from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExtractedField:
    """A single metadata field extracted from a PDF."""
    value: Any
    source: str  # 'pdf_metadata', 'first_page_text', 'doi_lookup'
    confidence: str  # 'high', 'medium', 'low'


@dataclass(frozen=True)
class ExtractedMetadata:
    """Metadata extracted from a PDF file."""
    title: ExtractedField | None = None
    doi: ExtractedField | None = None
    arxiv_id: ExtractedField | None = None
    authors: ExtractedField | None = None
    year: ExtractedField | None = None
    journal: ExtractedField | None = None
    abstract: ExtractedField | None = None
    warnings: tuple[str, ...] = ()
    page_count: int = 0


@dataclass(frozen=True)
class UploadItem:
    """A single PDF file in an upload batch."""
    id: str
    batch_id: str
    filename: str
    staging_key: str
    sha256: str
    status: str = 'staged'  # staged, extracting, ready, needs_review, conflict, confirmed, cancelled, failed
    extracted_metadata: dict[str, Any] = field(default_factory=dict)
    candidate_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    target_paper_id: str | None = None
    error: str | None = None
    created_at: str = ''
    updated_at: str = ''


@dataclass(frozen=True)
class UploadBatch:
    """A batch of PDFs being uploaded and reviewed before library ingestion."""
    id: str
    status: str = 'staging'  # staging, ready, reviewing, confirmed, cancelled, failed
    items: tuple[UploadItem, ...] = ()
    created_at: str = ''
    confirmed_at: str | None = None
    cancelled_at: str | None = None


@dataclass(frozen=True)
class MetadataProposal:
    """A proposed metadata change for a canonical paper."""
    id: str
    paper_id: str
    source: str  # 'pdf_extraction', 'ai_suggestion', 'crossref_lookup'
    status: str = 'pending'  # pending, accepted, rejected
    current_metadata: dict[str, Any] = field(default_factory=dict)
    proposed_metadata: dict[str, Any] = field(default_factory=dict)
    fields_changed: tuple[str, ...] = ()
    created_at: str = ''
    resolved_at: str | None = None
    resolved_by: str | None = None  # 'user', 'auto'
    evidence_ids: tuple[str, ...] = ()
    identity_conflict: str | None = None


@dataclass(frozen=True)
class MaterializationResult:
    """Result of materializing a remote PDF to local storage."""
    paper_id: str
    status: str  # 'materialized', 'already_local', 'pdf_missing', 'pdf_failed', 'pdf_skipped'
    asset_id: str | None = None
    sha256: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchMaterializationResult:
    """Result of batch PDF materialization."""
    total: int = 0
    materialized: int = 0
    already_local: int = 0
    missing: int = 0
    failed: int = 0
    skipped: int = 0
    results: tuple[MaterializationResult, ...] = ()


METADATA_FIELDS = ("title", "authors", "year", "journal", "doi", "arxiv_id", "openalex_id", "abstract")


def metadata_snapshot(paper) -> dict:
    return {field: list(getattr(paper, field)) if field == "authors" else getattr(paper, field) for field in METADATA_FIELDS}


def metadata_patch(values: dict) -> dict:
    """Validate trusted application inputs too, not only HTTP payloads."""
    from app.modules.literature.domain.canonical import normalize_identifier
    if not isinstance(values, dict) or set(values) - set(METADATA_FIELDS):
        raise ValueError("Unsupported metadata fields")
    result = {}
    for name, value in values.items():
        if name == "authors":
            if not isinstance(value, (list, tuple)) or len(value) > 100 or any(not isinstance(x, str) or not x.strip() or len(x) > 512 for x in value):
                raise ValueError("Invalid authors")
            result[name] = [x.strip() for x in value]
        elif name == "year":
            if value is not None and (type(value) is not int or not 1000 <= value <= 3000):
                raise ValueError("Invalid year")
            result[name] = value
        else:
            if value is not None and (not isinstance(value, str) or len(value) > (30000 if name == "abstract" else 1000)):
                raise ValueError(f"Invalid {name}")
            text = value.strip() if isinstance(value, str) else None
            if name == "title" and not text:
                raise ValueError("Title must not be blank")
            kinds = {"doi": "doi", "arxiv_id": "arxiv", "openalex_id": "openalex"}
            result[name] = normalize_identifier(text, kinds[name]) if name in kinds else text or None
    return result
