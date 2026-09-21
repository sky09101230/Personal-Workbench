from hashlib import sha256
import io
import os
from pathlib import Path
import re
import tempfile

from pypdf import PdfReader

from app.modules.literature.application.errors import PdfUnavailableError
from app.modules.literature.domain.models import Attachment, ProviderFile


MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class LocalLiteratureFiles:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.staging = self.root / "staging"
        self.originals = self.root / "originals"

    def stage_pdf(self, data: bytes, filename: str) -> tuple[str, str]:
        if not data or len(data) > MAX_UPLOAD_BYTES or not data.startswith(b"%PDF-"):
            raise ValueError("Upload must be a PDF no larger than 50 MiB")
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not reader.pages:
                raise ValueError("Encrypted or empty PDF is unsupported")
        except Exception as error:
            raise ValueError("PDF could not be read; encrypted or malformed files are unsupported") from error
        digest = sha256(data).hexdigest()
        self.staging.mkdir(parents=True, exist_ok=True)
        import uuid
        staging_key = f"{uuid.uuid4().hex}.pending"
        target = self.staging / staging_key
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
        if not re.fullmatch(r"[a-f0-9]{32}\.pending", staging_key):
            raise ValueError("Invalid staging key")
        path = self.staging / staging_key
        if path.is_symlink() or path.resolve().parent != self.staging.resolve():
            raise ValueError("Invalid staging path")
        return path

    def discard_staged(self, staging_key: str) -> None:
        self._staged_path(staging_key).unlink(missing_ok=True)

    def finalize_pdf(self, staging_key: str, sha256_hex: str, *, keep_staging: bool = False) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", sha256_hex):
            raise ValueError("Invalid content hash")
        self.originals.mkdir(parents=True, exist_ok=True)
        staging_path = self._staged_path(staging_key)
        if not staging_path.is_file():
            raise ValueError("Staged file not found")
        if sha256(staging_path.read_bytes()).hexdigest() != sha256_hex:
            raise ValueError("Staged file hash mismatch")
        target_name = f"{sha256_hex}.pdf"
        target = self.originals / target_name
        if target.is_symlink():
            raise ValueError("Invalid original file path")
        try:
            os.link(staging_path, target)
        except FileExistsError:
            if target.read_bytes() != staging_path.read_bytes():
                raise ValueError("Existing content-addressed file is inconsistent")
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
        if not self.staging.is_dir():
            return 0
        import time
        now = time.time()
        removed = 0
        for child in self.staging.iterdir():
            if child.name not in (protected or set()) and not child.is_symlink() and child.is_file() and child.suffix == ".pending":
                try:
                    if now - child.stat().st_mtime > max_age_seconds:
                        child.unlink()
                        removed += 1
                except OSError:
                    pass
        return removed

    def open(self, asset: Attachment, *, range_header: str | None = None) -> ProviderFile:
        key = asset.storage_key or ""
        if not re.fullmatch(r"[a-f0-9]{64}\.pdf", key):
            raise PdfUnavailableError("Invalid local asset")

        path = self.originals / key
        if not path.is_file():
            path = self.root / key
            if not path.is_file():
                raise PdfUnavailableError("Local file is unavailable")

        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match or not any(match.groups()):
                return ProviderFile(asset.filename, "application/pdf", (), 416, "0", f"bytes */{size}", "bytes")
            left, right = match.groups()
            if left:
                start, end = int(left), min(int(right), size - 1) if right else size - 1
            else:
                start, end = max(0, size - int(right)), size - 1
            if start >= size or start > end:
                return ProviderFile(asset.filename, "application/pdf", (), 416, "0", f"bytes */{size}", "bytes")
            status = 206
        stream = path.open("rb")
        stream.seek(start)

        def chunks():
            remaining = end - start + 1
            try:
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                stream.close()

        return ProviderFile(asset.filename, "application/pdf", chunks(), status, str(end - start + 1), f"bytes {start}-{end}/{size}" if status == 206 else None, "bytes", stream.close)
