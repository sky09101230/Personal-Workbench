"""Provider-independent scholarly identity; no I/O or source-specific imports."""

from dataclasses import dataclass, field
import re
import unicodedata
from urllib.parse import unquote, urlsplit

from app.modules.literature.domain.models import Paper


class IdentityConflictError(ValueError):
    def __init__(self, reason: str, candidates: tuple[str, ...] = ()) -> None:
        super().__init__(reason)
        self.candidates = candidates


@dataclass(frozen=True)
class Ingestion:
    paper: Paper
    origin: str
    origin_key: str
    evidence: dict[str, object] = field(default_factory=dict)
    priority: int = 50
    source: str = "manual"
    restore: bool = False


@dataclass(frozen=True)
class IngestResult:
    paper_id: str
    created: bool
    reason: str


def normalize_identifier(value: str | None, kind: str) -> str | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    if value.lower().startswith(("http://", "https://")):
        url = urlsplit(value)
        hosts = {"doi": {"doi.org", "dx.doi.org"}, "arxiv": {"arxiv.org", "www.arxiv.org"}, "openalex": {"openalex.org", "www.openalex.org"}}
        if url.netloc.casefold() not in hosts[kind]:
            raise ValueError(f"Invalid {kind} identifier host")
        value = unquote(url.path.lstrip("/"))
    if kind == "doi":
        value = re.sub(r"^doi:\s*", "", value, flags=re.I).casefold()
        pattern = r"10\.\d{4,9}/\S+"
    elif kind == "arxiv":
        value = re.sub(r"^(?:arxiv:\s*|abs/|pdf/)", "", value, flags=re.I)
        value = re.sub(r"v\d+$", "", value.removesuffix(".pdf"), flags=re.I).casefold()
        pattern = r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})"
    else:
        value = value.upper()
        pattern = r"W\d+"
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid {kind} identifier")
    return value


def title_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in value).split())


def identifiers(paper: Paper) -> dict[str, str]:
    result = {}
    for kind, value in (("doi", paper.doi), ("arxiv", paper.arxiv_id), ("openalex", paper.openalex_id)):
        normalized = normalize_identifier(value, kind)
        if normalized:
            result[kind] = normalized
    if result.get("doi", "").startswith("10.48550/arxiv."):
        arxiv = normalize_identifier(result["doi"][len("10.48550/arxiv."):], "arxiv")
        if result.get("arxiv") not in (None, arxiv):
            raise IdentityConflictError("Preprint DOI and arXiv identifier disagree")
        result["arxiv"] = arxiv
    return result


def formal_doi(value: str | None) -> str | None:
    return value if value and not value.startswith("10.48550/arxiv.") else None


def compatible(existing: Paper, incoming: Paper) -> None:
    left, right = identifiers(existing), identifiers(incoming)
    a, b = formal_doi(left.get("doi")), formal_doi(right.get("doi"))
    if a and b and a != b:
        raise IdentityConflictError("Conflicting formal DOI", (existing.id,))
    for kind in ("arxiv", "openalex"):
        if left.get(kind) and right.get(kind) and left[kind] != right[kind]:
            raise IdentityConflictError(f"Conflicting {kind}; identifier correction requires reviewed evidence", (existing.id,))


def corroborated_title(existing: Paper, incoming: Paper) -> bool:
    key = title_key(incoming.title)
    return bool(
        len(key) >= 12 and key not in {"untitled paper", "untitled document"}
        and key == title_key(existing.title)
        and existing.year is not None and existing.year == incoming.year
        and {title_key(x) for x in existing.authors} & {title_key(x) for x in incoming.authors}
    )
