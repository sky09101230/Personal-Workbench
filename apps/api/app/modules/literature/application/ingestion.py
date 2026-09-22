from collections.abc import Callable
from dataclasses import dataclass, replace
import re
from uuid import uuid4

from app.modules.literature.application.ports import CanonicalLibrary, LiteratureFileStore
from app.modules.literature.application.errors import LiteratureResourceNotFoundError
from app.modules.literature.domain.canonical import Ingestion, IngestResult
from app.modules.literature.domain.models import Attachment, Paper


@dataclass(frozen=True)
class LiteratureIngestionService:
    repository: CanonicalLibrary
    files: LiteratureFileStore
    radar_export: Callable[[str], dict[str, object] | None]

    def save_radar(self, recommendation_id: str) -> IngestResult:
        exported = self.radar_export(recommendation_id)
        if exported is None:
            raise LiteratureResourceNotFoundError("Radar recommendation not found")
        metadata = exported["paper"]
        published = str(metadata.get("published_at") or "")
        year = int(published[:4]) if re.match(r"^\d{4}", published) else None
        paper = Paper("", str(metadata["title"]), tuple(metadata.get("authors", ())), metadata.get("abstract"), year, metadata.get("venue"), metadata.get("doi"), arxiv_id=metadata.get("arxiv_id"), openalex_id=metadata.get("openalex_id"))
        appearances = exported["appearances"]
        selected = next(x for x in appearances if x["recommendation_id"] == recommendation_id)
        paper = replace(paper, date_evidence=selected.get("date_evidence", {}))
        # A News discovery group is not scholarly identity evidence for every appearance.
        evidence = {**selected, "metadata_scope": "current_discovery_snapshot", "unverified_related_appearances": [item for item in appearances if item["recommendation_id"] != recommendation_id]}
        return self.repository.ingest(Ingestion(paper, "radar", recommendation_id, evidence, 60, "radar_evidence", True))

    def upload_pdf(self, data: bytes, filename: str, *, paper_id: str | None = None, title: str | None = None, role: str = "primary"):
        if role not in {"primary", "preprint", "supplementary"}:
            raise ValueError("Invalid asset role")
        if not paper_id and role != "primary":
            raise ValueError("Select an existing paper for preprint or supplementary association")
        if paper_id and self.repository.get_paper(paper_id) is None:
            raise LiteratureResourceNotFoundError("Paper not found")
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:240] or "paper.pdf"
        storage_key, digest = self.files.store_pdf(data, filename)
        # File hash identifies an incomplete upload only; an explicit target owns association.
        origin_key = f"{paper_id or 'new'}:{role}:{digest}"
        paper = self.repository.get_paper(paper_id).paper if paper_id else Paper("", title or filename.removesuffix(".pdf"))
        return self.repository.ingest_asset(
            Ingestion(paper, "manual_pdf", origin_key, {"filename": filename, "sha256": digest, "role": role}, 10, "manual_pdf", True),
            Attachment(f"asset:{uuid4()}", "", filename, "application/pdf", True, "local_file", role=role, storage_kind="local", storage_key=storage_key, sha256=digest),
        )
