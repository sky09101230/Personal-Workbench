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

    def store_pdf(self, data: bytes, filename: str) -> tuple[str, str]:
        if not data or len(data) > MAX_UPLOAD_BYTES or not data.startswith(b"%PDF-"):
            raise ValueError("Upload must be a PDF no larger than 50 MiB")
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not reader.pages:
                raise ValueError("Encrypted or empty PDF is unsupported")
        except Exception as error:
            raise ValueError("PDF could not be read; encrypted or malformed files are unsupported") from error
        digest = sha256(data).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{digest}.pdf"
        # Publish only complete files; concurrent uploads never observe partial bytes.
        with tempfile.NamedTemporaryFile(dir=self.root, suffix=".pending", delete=False) as stream:
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
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != data:
                    raise ValueError("Existing content-addressed file is inconsistent")
        finally:
            temporary.unlink()
        return target.name, digest

    def open(self, asset: Attachment, *, range_header: str | None = None) -> ProviderFile:
        key = asset.storage_key or ""
        if not re.fullmatch(r"[a-f0-9]{64}\.pdf", key):
            raise PdfUnavailableError("Invalid local asset")
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
