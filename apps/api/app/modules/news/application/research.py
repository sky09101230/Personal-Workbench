import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, replace
from urllib.parse import unquote, urlsplit

from app.modules.news.domain.research_models import (
    PaperResearchIngest,
    PaperResearchPaperInput,
)


_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ARXIV_PATTERN = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})$",
    re.IGNORECASE,
)
_OPENALEX_PATTERN = re.compile(r"^W\d+$", re.IGNORECASE)


def normalize_research_ingest(payload: PaperResearchIngest) -> PaperResearchIngest:
    return replace(
        payload,
        task_key=_normalized_key(payload.task_key),
        run_key=_normalized_key(payload.run_key),
        run_kind=_normalized_key(payload.run_kind),
        ingest_identity=(
            _normalized_key(payload.ingest_identity)
            if payload.ingest_identity is not None
            else None
        ),
        warnings=_clean_values(payload.warnings),
        source_status=tuple(dict(item) for item in payload.source_status),
        profile=dict(payload.profile),
        search_window=dict(payload.search_window),
        zotero_context=dict(payload.zotero_context),
        diagnostics=dict(payload.diagnostics),
        papers=tuple(normalize_research_paper(paper) for paper in payload.papers),
    )


def normalize_research_paper(paper: PaperResearchPaperInput) -> PaperResearchPaperInput:
    selection_kind = _normalized_key(paper.selection_kind)
    ai_summary = paper.ai_summary.strip()
    if selection_kind == "recommended" and not ai_summary:
        raise ValueError("ai_summary must not be empty for recommended papers")
    return replace(
        paper,
        title=_required_text(paper.title, "title"),
        authors=_clean_values(paper.authors),
        doi=normalize_doi(paper.doi),
        arxiv_id=normalize_arxiv_id(paper.arxiv_id),
        openalex_id=normalize_openalex_id(paper.openalex_id),
        publication_type=_optional_text(paper.publication_type),
        topics=_clean_values(paper.topics),
        matched_topics=_clean_values(paper.matched_topics),
        ai_summary=ai_summary,
        recommendation_reason=_required_text(
            paper.recommendation_reason,
            "recommendation_reason",
        ),
        relationship_to_library=_optional_text(paper.relationship_to_library),
        selection_kind=selection_kind,
        source=dict(paper.source),
        date_evidence=dict(paper.date_evidence),
        zotero_relationship=dict(paper.zotero_relationship),
        evidence=dict(paper.evidence),
    )


def research_payload_digest(payload: PaperResearchIngest) -> str:
    canonical = json.dumps(
        asdict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.lower().startswith(("http://", "https://")):
        parsed = urlsplit(normalized)
        if parsed.netloc.casefold() not in {"doi.org", "dx.doi.org"}:
            raise ValueError("doi URL must use doi.org or dx.doi.org")
        normalized = unquote(parsed.path.lstrip("/"))
    elif normalized.casefold().startswith("doi:"):
        normalized = normalized[4:].strip()
    normalized = normalized.casefold()
    if not _DOI_PATTERN.fullmatch(normalized):
        raise ValueError("doi must be a valid DOI")
    return normalized


def normalize_arxiv_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.lower().startswith(("http://", "https://")):
        parsed = urlsplit(normalized)
        if parsed.netloc.casefold() not in {"arxiv.org", "www.arxiv.org"}:
            raise ValueError("arxiv_id URL must use arxiv.org")
        normalized = re.sub(r"^/(?:abs|pdf)/", "", parsed.path, flags=re.IGNORECASE)
        normalized = normalized.removesuffix(".pdf")
    normalized = re.sub(r"^arxiv:\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"v\d+$", "", normalized, flags=re.IGNORECASE).casefold()
    if not _ARXIV_PATTERN.fullmatch(normalized):
        raise ValueError("arxiv_id must be a valid arXiv identifier")
    return normalized


def normalize_openalex_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.lower().startswith(("http://", "https://")):
        parsed = urlsplit(normalized)
        if parsed.netloc.casefold() not in {"openalex.org", "www.openalex.org"}:
            raise ValueError("openalex_id URL must use openalex.org")
        normalized = parsed.path.strip("/")
    normalized = normalized.upper()
    if not _OPENALEX_PATTERN.fullmatch(normalized):
        raise ValueError("openalex_id must be a valid OpenAlex work identifier")
    return normalized


def canonical_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    return " ".join(
        "".join(character if character.isalnum() else " " for character in normalized).split()
    )


def canonical_title_year(title: str, published_at: str | None) -> str:
    year = published_at[:4] if published_at and re.match(r"^\d{4}", published_at) else "unknown"
    return f"{canonical_title(title)}|{year}"


def _normalized_key(value: str) -> str:
    return _required_text(value, "key").casefold()


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _clean_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
