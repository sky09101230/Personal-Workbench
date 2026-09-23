"""Standalone, stdlib-only, read-only Zotero bridge. Python 3.11+."""
import argparse
from contextlib import closing
from hashlib import md5, sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import stat
import tempfile
import time
from urllib.parse import urlsplit

MAX_BYTES = 50 * 1024 * 1024
PORT = 23120


class AgentError(Exception):
    pass


def safe_path(path):
    # Reject junctions/reparse points as well as Unix symlinks, including parents.
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            s = part.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 0x400:
                raise AgentError('unsafe_path')
    return path


class ZoteroFiles:
    def __init__(self, directory):
        self.root = safe_path(Path(directory).absolute())

    def signature(self):
        result = {}
        for suffix in ('', '-wal', '-journal'):
            p = safe_path(self.root / ('zotero.sqlite' + suffix))
            if p.exists():
                s = p.stat()
                result[suffix] = (s.st_size, s.st_mtime_ns, s.st_ino)
        return result

    def locate(self, request):
        if set(request) != {'library_id', 'item_key', 'parent_key'} or not all(isinstance(v, str) for v in request.values()):
            raise AgentError('invalid_source')
        if not re.fullmatch(r'[0-9]{1,20}', request['library_id']) or not all(re.fullmatch(r'[A-Z0-9]{8}', request[k]) for k in ('item_key', 'parent_key')):
            raise AgentError('invalid_source')
        for _ in range(3):
            before = self.signature()
            if '' not in before:
                raise AgentError('source_unavailable')
            with tempfile.TemporaryDirectory(prefix='workbench-zotero-') as tmp:
                target = Path(tmp) / 'zotero.sqlite'
                for suffix in before:
                    shutil.copyfile(self.root / ('zotero.sqlite' + suffix), str(target) + suffix)
                if before != self.signature():
                    continue
                with closing(sqlite3.connect(target)) as db:
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise AgentError('snapshot_invalid')
                    account = db.execute("SELECT value FROM settings WHERE setting='account' AND key='userID'").fetchone()
                    if not account or str(account[0]) != request['library_id']:
                        raise AgentError('account_mismatch')
                    row = db.execute("SELECT i.version,p.key,a.path,a.contentType,a.linkMode FROM items i JOIN libraries l USING(libraryID) JOIN itemAttachments a USING(itemID) JOIN items p ON p.itemID=a.parentItemID AND p.libraryID=i.libraryID WHERE l.type='user' AND i.key=?", (request['item_key'],)).fetchone()
                    if not row:
                        raise AgentError('source_unavailable')
                    version, parent, locator, content_type, mode = row
                    if parent != request['parent_key']:
                        raise AgentError('parent_mismatch')
                    if db.execute("SELECT 1 FROM sqlite_master WHERE name='deletedItems'").fetchone():
                        if db.execute("SELECT 1 FROM deletedItems d JOIN items i USING(itemID) JOIN libraries l USING(libraryID) WHERE l.type='user' AND i.key IN (?,?)", (parent, request['item_key'])).fetchone():
                            raise AgentError('source_unavailable')
                    if mode not in (0, 1) or not locator or not locator.startswith('storage:'):
                        raise AgentError('linked_file_unsupported')
                    if content_type != 'application/pdf':
                        raise AgentError('not_pdf')
                name = locator[len('storage:'):]
                if name in ('', '.', '..') or any(c in name for c in '/\\:\x00'):
                    raise AgentError('unsafe_path')
                path = safe_path(self.root / 'storage' / request['item_key'] / name)
                if not path.is_file():
                    raise AgentError('source_unavailable')
                return path, str(version)
        raise AgentError('source_changed')

    def export(self, request):
        path, version = self.locate(request)
        before = path.stat()
        if before.st_size > MAX_BYTES:
            raise AgentError('size_limit')
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise AgentError('size_limit')
        if not data.startswith(b'%PDF-'):
            raise AgentError('not_pdf')
        # Re-read metadata and bytes after export, so only a stable snapshot is sent.
        after_path, after_version = self.locate(request)
        after = after_path.stat()
        if (path, version, before.st_size, before.st_mtime_ns, before.st_ino) != (after_path, after_version, after.st_size, after.st_mtime_ns, after.st_ino):
            raise AgentError('source_changed')
        with safe_path(after_path).open('rb') as stream:
            digest = sha256()
            size = 0
            for chunk in iter(lambda: stream.read(65536), b''):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise AgentError('size_limit')
                digest.update(chunk)
        if digest.hexdigest() != sha256(data).hexdigest():
            raise AgentError('source_changed')
        observation = {**request, 'version': version, 'sha256': digest.hexdigest(), 'md5': md5(data).hexdigest(), 'size_bytes': len(data)}
        return data, {'schema_version': 1, 'before': observation, 'after': dict(observation)}


class AgentServer(HTTPServer):
    # Serial handling intentionally bounds live PDF buffers to one transfer.
    def __init__(self, directory, origin, port=PORT, clock=time.monotonic):
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or '*' in origin:
            raise ValueError('Origin must be an exact http(s) origin without a trailing slash')
        self.origin, self.files, self.clock = origin, ZoteroFiles(directory), clock
        self.code = secrets.token_urlsafe(32)
        self.code_expires = clock() + 300
        self.session, self.expires = '', 0
        self.attempts = []
        super().__init__(('127.0.0.1', port), Handler)

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(15)
        return sock, addr


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log credentials or library metadata.

    def allowed(self):
        return self.headers.get_all('Origin') == [self.server.origin] and self.headers.get_all('Host') == [f'127.0.0.1:{self.server.server_port}']

    def reply(self, status, payload=None, data=None, observation=None):
        body = data if data is not None else json.dumps(payload).encode()
        self.send_response(status)
        if self.allowed():
            self.send_header('Access-Control-Allow-Origin', self.server.origin)
            self.send_header('Access-Control-Allow-Headers', 'authorization,content-type')
            self.send_header('Access-Control-Allow-Methods', 'POST,OPTIONS')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Access-Control-Expose-Headers', 'X-Zotero-Observation')
        self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Type', 'application/pdf' if data is not None else 'application/json')
        self.send_header('Content-Length', str(len(body)))
        if observation:
            self.send_header('X-Zotero-Observation', json.dumps(observation, separators=(',', ':')))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.reply(200 if self.allowed() else 403, {})

    def do_POST(self):
        try:
            if not self.allowed():
                return self.reply(403, {'error': 'origin_denied'})
            if self.path not in ('/v1/pair', '/v1/export', '/v1/disconnect'):
                return self.reply(404, {'error': 'not_found'})
            now = self.server.clock()
            if self.path != '/v1/pair' and (not self.server.session or now >= self.server.expires or not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.session)):
                return self.reply(401, {'error': 'pairing_required'})
            lengths = self.headers.get_all('Content-Length') or []
            if len(lengths) != 1 or self.headers.get('Transfer-Encoding') or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 2048 or self.headers.get('Content-Type') != 'application/json':
                return self.reply(400, {'error': 'invalid_request'})
            value = json.loads(self.rfile.read(int(lengths[0])))
            if not isinstance(value, dict):
                raise AgentError('invalid_request')
            if self.path == '/v1/pair':
                self.server.attempts = [t for t in self.server.attempts if now - t < 60]
                if len(self.server.attempts) >= 5:
                    return self.reply(429, {'error': 'pairing_rate_limited'})
                self.server.attempts.append(now)
                code = value.get('code')
                if set(value) != {'code'} or not isinstance(code, str) or not self.server.code or now >= self.server.code_expires or not secrets.compare_digest(code, self.server.code):
                    return self.reply(401, {'error': 'pairing_required'})
                self.server.code = ''
                self.server.session = secrets.token_urlsafe(32)
                self.server.expires = now + 1800
                return self.reply(200, {'schema_version': 1, 'token': self.server.session, 'expires_in': 1800})
            if self.path == '/v1/disconnect':
                self.server.session = ''
                return self.reply(200, {'disconnected': True})
            data, observation = self.server.files.export(value)
            if self.server.clock() >= self.server.expires:
                return self.reply(401, {'error': 'pairing_required'})
            self.reply(200, data=data, observation=observation)
        except AgentError as error:
            self.reply(409, {'error': str(error)})
        except (ValueError, KeyError, TypeError):
            self.reply(400, {'error': 'invalid_request'})
        except (OSError, sqlite3.Error):
            try:
                self.reply(503, {'error': 'source_unavailable'})
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zotero-dir', required=True)
    parser.add_argument('--origin', required=True)
    args = parser.parse_args()
    with AgentServer(args.zotero_dir, args.origin) as server:
        print(f'Local Zotero agent: http://127.0.0.1:{PORT}\nAllowed Workbench: {args.origin}\nPairing code (5 minutes, one use): {server.code}\nSession: 30 minutes. Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
