from hashlib import sha256, file_digest, md5
import io
import os
from pathlib import Path
import re
import tempfile

from pypdf import PdfReader

from app.modules.literature.application.errors import LocalAssetError, PdfSizeLimitError
from app.modules.literature.domain.models import AssetIntegrity, Attachment, ProviderFile, StagedPdf, MAX_SOURCE_PDF_BYTES


MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _validate_pdf(stream):
    stream.seek(0)
    if stream.read(5) != b'%PDF-':
        raise ValueError('A PDF signature is required')
    stream.seek(0)
    try:
        reader = PdfReader(stream)
        if reader.is_encrypted or not reader.pages:
            raise ValueError('Encrypted or empty PDF is unsupported')
    except Exception as error:
        raise ValueError('PDF could not be read; encrypted or malformed files are unsupported') from error


def _resolved(path: Path) -> Path:
    resolved = path.resolve()
    # Windows realpath can retain the extended prefix while a parent is created
    # concurrently. Normalize equivalent drive/UNC spellings before containment.
    value = str(resolved)
    if os.name == "nt":
        if value.startswith("\\\\?\\UNC\\"):
            return Path("\\\\" + value[8:])
        if value.startswith("\\\\?\\") and re.match(r"[A-Za-z]:\\", value[4:]):
            return Path(value[4:])
    return resolved


class LocalLiteratureFiles:
    def __init__(self, root: str) -> None:
        self.root = _resolved(Path(root))
        self.staging = self.root / "staging"
        self.originals = self.root / "originals"

    def _directory(self, path: Path, *, create: bool = False) -> Path:
        if _resolved(self.root) != self.root or self.root.is_symlink():
            raise ValueError("Invalid Vault root")
        if path not in {self.root, self.staging, self.originals} or path.is_symlink() or _resolved(path) != path:
            raise ValueError("Invalid Vault directory")
        if getattr(path, "is_junction", lambda: False)():
            raise ValueError("Invalid Vault directory")
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _contained(self, path: Path, directory: Path) -> Path:
        self._directory(directory)
        if path.parent != directory or path.is_symlink() or _resolved(path).parent != directory or getattr(path, "is_junction", lambda: False)():
            raise ValueError("Invalid Vault file path")
        return path

    def stage_pdf(self, data: bytes, filename: str) -> tuple[str, str]:
        if not data or len(data) > MAX_UPLOAD_BYTES or not data.startswith(b"%PDF-"):
            raise ValueError("Upload must be a PDF no larger than 50 MiB")
        _validate_pdf(io.BytesIO(data))
        digest = sha256(data).hexdigest()
        self._directory(self.staging, create=True)
        import uuid
        staging_key = f"{uuid.uuid4().hex}.pending"
        target = self._staged_path(staging_key)
        with tempfile.NamedTemporaryFile(dir=self.staging, suffix=".pending", delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            except Exception:
                stream.close()
                temporary.unlink()
                raise
        try:
            os.link(temporary, target)
        finally:
            temporary.unlink()
        return staging_key, digest

    def _staged_path(self, staging_key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}\.(pending|acquiring)", staging_key):
            raise ValueError("Invalid staging key")
        return self._contained(self.staging / staging_key, self.staging)

    def stage_source_pdf(self, chunks, filename):
        import uuid
        self._directory(self.staging, create=True)
        key = uuid.uuid4().hex + '.acquiring'
        target = self._staged_path(key)
        digest, source_hash, size = sha256(), md5(), 0
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.staging, suffix='.acquiring', delete=False) as stream:
                temporary = Path(stream.name)
                for chunk in chunks:
                    size += len(chunk)
                    if size > MAX_SOURCE_PDF_BYTES:
                        raise PdfSizeLimitError('Source PDF exceeds 256 MiB')
                    stream.write(chunk)
                    digest.update(chunk)
                    source_hash.update(chunk)
                stream.flush()
                _validate_pdf(stream)
                os.fsync(stream.fileno())
            os.link(temporary, target)
            return StagedPdf(key, digest.hexdigest(), source_hash.hexdigest(), size, 'local')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def discard_staged(self, staging_key: str) -> None:
        self._staged_path(staging_key).unlink(missing_ok=True)

    def finalize_pdf(self, staging_key: str, sha256_hex: str, *, keep_staging: bool = False) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", sha256_hex):
            raise ValueError("Invalid content hash")
        self._directory(self.originals, create=True)
        staging_path = self._staged_path(staging_key)
        if not staging_path.is_file():
            raise ValueError("Staged file not found")
        target_name = f"{sha256_hex}.pdf"
        target = self._contained(self.originals / target_name, self.originals)
        temporary = None
        try:
            # Independent inode: a retained staging file cannot mutate the original.
            with staging_path.open("rb") as source, tempfile.NamedTemporaryFile(dir=self.originals, suffix=".pending", delete=False) as output:
                temporary = Path(output.name)
                digest = sha256()
                for chunk in iter(lambda: source.read(65536), b""):
                    digest.update(chunk)
                    output.write(chunk)
                if digest.hexdigest() != sha256_hex:
                    raise ValueError("Staged file hash mismatch")
                output.flush()
                os.fsync(output.fileno())
            self._contained(target, self.originals)
            try:
                os.link(temporary, target)
            except FileExistsError:
                with target.open("rb") as existing:
                    if file_digest(existing, "sha256").hexdigest() != sha256_hex:
                        raise ValueError("Existing content-addressed file is inconsistent")
                if keep_staging and os.path.samefile(staging_path, target):
                    # Detach a retained staging link created by the pre-Vault implementation.
                    self._staged_path(staging_key)
                    os.replace(temporary, staging_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        if not keep_staging:
            staging_path.unlink()
        return target_name

    def store_pdf(self, data: bytes, filename: str) -> tuple[str, str]:
        staging_key, digest = self.stage_pdf(data, filename)
        target_name = self.finalize_pdf(staging_key, digest)
        return target_name, digest

    def cleanup_staging(self, max_age_seconds: int = 3600, *, protected: set[str] | None = None) -> int:
        if max_age_seconds < 0:
            raise ValueError("Invalid cleanup age")
        self._directory(self.staging)
        if not self.staging.is_dir():
            return 0
        import time
        now = time.time()
        removed = 0
        for child in self.staging.iterdir():
            if child.name not in (protected or set()) and not child.is_symlink() and child.is_file() and child.suffix == ".pending":
                try:
                    if now - child.stat().st_mtime > max_age_seconds:
                        self._contained(child, self.staging).unlink()
                        removed += 1
                except OSError:
                    pass
        return removed

    def _verified_open(self, asset: Attachment):
        if asset.storage_kind != "local":
            raise LocalAssetError("unsupported_backend")
        key = asset.storage_key or ""
        if not re.fullmatch(r"[a-f0-9]{64}\.pdf", key) or asset.sha256 not in (None, key[:-4]):
            raise LocalAssetError("invalid")
        stream = None
        try:
            path = self._contained(self.originals / key, self.originals)
            if not path.exists():
                path = self._contained(self.root / key, self.root)
            if not path.is_file():
                raise LocalAssetError("invalid" if path.exists() else "missing")
            stream = path.open("rb")
            digest = file_digest(stream, "sha256").hexdigest()
            size = stream.seek(0, os.SEEK_END)
            if digest != key[:-4]:
                raise LocalAssetError("corrupt")
            stream.seek(0)
            return stream, size
        except Exception as error:
            if stream is not None:
                stream.close()
            if isinstance(error, ValueError):
                raise LocalAssetError("invalid") from error
            if isinstance(error, FileNotFoundError):
                raise LocalAssetError("missing") from error
            if isinstance(error, OSError):
                raise LocalAssetError("unreadable") from error
            raise

    def inspect(self, asset: Attachment) -> AssetIntegrity:
        if asset.storage_kind == "zotero":
            return AssetIntegrity(asset.id, "remote_only")
        try:
            stream, size = self._verified_open(asset)
            stream.close()
            return AssetIntegrity(asset.id, "verified", size, asset.storage_key[:-4])
        except LocalAssetError as error:
            return AssetIntegrity(asset.id, error.state)

    def open(self, asset: Attachment, *, range_header: str | None = None) -> ProviderFile:
        stream, size = self._verified_open(asset)

        start, end, status = 0, size - 1, 200
        if range_header:
            match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", range_header)
            if not match or not any(match.groups()):
                stream.close()
                return ProviderFile(asset.filename, "application/pdf", (), 416, "0", f"bytes */{size}", "bytes")
            left, right = match.groups()
            if left:
                start, end = int(left), min(int(right), size - 1) if right else size - 1
            else:
                start, end = max(0, size - int(right)), size - 1
            if start >= size or start > end:
                stream.close()
                return ProviderFile(asset.filename, "application/pdf", (), 416, "0", f"bytes */{size}", "bytes")
            status = 206
        stream.seek(start)

        def chunks():
            remaining = end - start + 1
            try:
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        raise LocalAssetError("corrupt")
                    remaining -= len(chunk)
                    yield chunk
            finally:
                stream.close()

        return ProviderFile(asset.filename, "application/pdf", chunks(), status, str(end - start + 1), f"bytes {start}-{end}/{size}" if status == 206 else None, "bytes", stream.close)
