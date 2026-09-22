"""Read-only registered Zotero files; live DB locks are respected via checked snapshots."""

from contextlib import closing
from hashlib import file_digest
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from threading import RLock

from app.modules.literature.application.errors import PdfUnavailableError, ProviderAuthenticationError
from app.modules.literature.domain.models import ProviderFile, MAX_SOURCE_PDF_BYTES


class LocalZoteroFiles:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.database = self.directory / 'zotero.sqlite'
        self._signature = None
        self._temporary = None
        self._lock = RLock()
        self._temp_root = Path(tempfile.gettempdir()).resolve()

    def _source_signature(self):
        result = {}
        for suffix in ('', '-wal', '-journal'):
            path = Path(str(self.database) + suffix)
            if path.exists():
                stat = path.stat()
                result[suffix] = (stat.st_size, stat.st_mtime_ns, stat.st_ino)
        return result

    def _cleanup(self, temporary):
        target = Path(temporary.name).resolve()
        if target == self._temp_root or not target.is_relative_to(self._temp_root):
            raise PdfUnavailableError('Unexpected local snapshot directory')
        temporary.cleanup()

    def _snapshot(self):
        signature = self._source_signature()
        if '' not in signature:
            raise PdfUnavailableError('Local Zotero database is unavailable')
        if signature == self._signature and self._temporary is not None:
            return Path(self._temporary.name) / 'zotero.sqlite'
        for _ in range(3):
            signature = self._source_signature()
            temporary = tempfile.TemporaryDirectory(prefix='zotero-readonly-', dir=self._temp_root, ignore_cleanup_errors=True)
            destination = Path(temporary.name) / 'zotero.sqlite'
            try:
                for suffix in signature:
                    shutil.copyfile(str(self.database) + suffix, str(destination) + suffix)
                if self._source_signature() != signature:
                    self._cleanup(temporary)
                    continue
                # Any copied hot journal is recovered only in this disposable copy.
                with closing(sqlite3.connect(destination)) as c:
                    if c.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise PdfUnavailableError('Local Zotero snapshot failed integrity checking')
                if self._temporary is not None:
                    self._cleanup(self._temporary)
                self._temporary, self._signature = temporary, signature
                return destination
            except Exception:
                self._cleanup(temporary)
                raise
        raise PdfUnavailableError('Local Zotero database changed while taking a snapshot')

    def _locate(self, reference):
        with self._lock:
            snapshot = self._snapshot()
            with closing(sqlite3.connect(snapshot.as_uri() + '?mode=ro', uri=True)) as c:
                c.row_factory = sqlite3.Row
                account = c.execute("SELECT value FROM settings WHERE setting='account' AND key='userID'").fetchone()
                if not account or str(account[0]) != reference.library_id:
                    raise ProviderAuthenticationError('Local Zotero account does not match the source reference')
                row = c.execute("SELECT i.key,i.version,p.key AS parent_key,a.path,a.contentType,a.linkMode FROM items i JOIN libraries l USING(libraryID) JOIN itemAttachments a USING(itemID) JOIN items p ON p.itemID=a.parentItemID WHERE l.type='user' AND i.key=?", (reference.item_key,)).fetchone()
                if not row or row['contentType'] != 'application/pdf' or row['linkMode'] not in (0, 1) or not row['path'].startswith('storage:'):
                    return None
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='deletedItems'").fetchone():
                    if c.execute("SELECT 1 FROM deletedItems d JOIN items i ON i.itemID=d.itemID WHERE i.libraryID IN (SELECT libraryID FROM libraries WHERE type='user') AND i.key IN (?,?)", (reference.item_key, row['parent_key'])).fetchone():
                        return None
                record = dict(row)
        storage = (self.directory / 'storage').resolve()
        attachment_dir = storage / reference.item_key
        file = attachment_dir / record['path'].removeprefix('storage:')
        if attachment_dir.is_symlink() or attachment_dir.resolve() != attachment_dir or not attachment_dir.is_relative_to(storage):
            return None
        if file.is_symlink() or not file.resolve().is_relative_to(attachment_dir) or not file.is_file():
            return None
        return file, record

    def describe(self, reference):
        located = self._locate(reference)
        if not located:
            return None
        file, record = located
        before = file.stat()
        with file.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                return None
            stream.seek(0)
            digest = file_digest(stream, 'md5').hexdigest() if before.st_size <= MAX_SOURCE_PDF_BYTES else None
        after = file.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise PdfUnavailableError('Local PDF changed during source inspection')
        return {'key': reference.item_key, 'version': f"local:{record['version']}:{before.st_mtime_ns}:{before.st_size}", 'library': {'id': reference.library_id}, 'local_locator': f"storage/{reference.item_key}/{file.name}", 'data': {'itemType': 'attachment', 'parentItem': record['parent_key'], 'filename': file.name, 'contentType': 'application/pdf', 'linkMode': 'imported_file' if record['linkMode'] == 0 else 'imported_url', 'md5': digest}}

    def open(self, reference, *, filename, range_header=None):
        located = self._locate(reference)
        if not located:
            raise PdfUnavailableError('Registered local Zotero PDF is unavailable')
        file, _ = located
        stream = file.open('rb')
        size = stream.seek(0, 2)
        start, end, status = 0, size - 1, 200
        if range_header:
            match = re.fullmatch(r'bytes=([0-9]{0,20})-([0-9]{0,20})', range_header)
            if not match or not any(match.groups()):
                stream.close()
                return ProviderFile(filename, 'application/pdf', (), 416, '0', f'bytes */{size}', 'bytes')
            left, right = match.groups()
            start = int(left) if left else max(0, size - int(right))
            end = min(int(right), size - 1) if left and right else size - 1
            if start > end or start >= size:
                stream.close()
                return ProviderFile(filename, 'application/pdf', (), 416, '0', f'bytes */{size}', 'bytes')
            status = 206
        stream.seek(start)
        def chunks():
            remaining = end - start + 1
            try:
                while remaining:
                    data = stream.read(min(65536, remaining))
                    if not data:
                        raise PdfUnavailableError('Local PDF changed while streaming')
                    remaining -= len(data)
                    yield data
            finally:
                stream.close()
        return ProviderFile(filename, 'application/pdf', chunks(), status, str(end - start + 1), f'bytes {start}-{end}/{size}' if status == 206 else None, 'bytes', stream.close)

    def close(self):
        with self._lock:
            if self._temporary is not None:
                self._cleanup(self._temporary)
                self._temporary = None
                self._signature = None
