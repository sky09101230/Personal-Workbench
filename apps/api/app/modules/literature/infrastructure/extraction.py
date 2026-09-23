"""PDF metadata extraction with optional OCR and DOI title verification."""

import io
import re
from difflib import SequenceMatcher
from urllib.parse import quote
from app.modules.literature.domain.workflow import ExtractedField, ExtractedMetadata
from app.modules.literature.domain.canonical import normalize_identifier

import pypdf
import httpx


_DOI_RE = re.compile(r'\b(10\.\d{4,9}\s*/\s*[-._;()/:A-Z0-9]+)', re.IGNORECASE)
_ARXIV_RE = re.compile(r'(?:arxiv[:\s]*)(\d{4}\.\d{4,5}(?:v\d+)?)', re.IGNORECASE)


def _selected_pages(page_count: int) -> tuple[int, ...]:
    return tuple(dict.fromkeys((*range(min(2, page_count)), *range(max(0, page_count - 2), page_count))))


def _ocr_text(data: bytes, page_indexes: tuple[int, ...]) -> str:
    """OCR selected pages when optional OCR dependencies are installed."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    try:
        document = fitz.open(stream=data, filetype="pdf")
        pages = []
        for index in page_indexes:
            page = document[index]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            pages.append(pytesseract.image_to_string(image, config="--psm 3"))
        return "\n".join(pages)
    except Exception:
        return ""


def _title_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _lookup_doi_title(doi: str) -> str | None:
    try:
        response = httpx.get(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            headers={"Accept": "application/json"},
            timeout=3.0,
        )
        response.raise_for_status()
        titles = response.json().get("message", {}).get("title", [])
        return str(titles[0]).strip() if titles else None
    except Exception:
        return None


def _fetch_doi_bibtex(doi: str) -> dict[str, object]:
    try:
        response = httpx.get(
            f"https://doi.org/{quote(doi, safe='')}",
            headers={"Accept": "application/x-bibtex"},
            timeout=3.0,
        )
        response.raise_for_status()
        text = response.text
        fields: dict[str, object] = {}
        for key in ("title", "author", "journal", "year", "doi"):
            match = re.search(rf"\b{key}\s*=\s*[{{\"](.*?)[}}\"]\s*,?\s*(?:\n|$)", text, re.IGNORECASE)
            if match:
                value = re.sub(r"\s+", " ", match.group(1)).strip()
                if key == "author":
                    fields[key] = tuple(part.strip() for part in re.split(r"\s+and\s+", value, flags=re.IGNORECASE) if part.strip())
                else:
                    fields[key] = value
        return fields
    except Exception:
        return {}


def _fetch_crossref_work(doi: str) -> dict[str, object]:
    try:
        response = httpx.get(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            headers={"Accept": "application/json"},
            timeout=3.0,
        )
        response.raise_for_status()
        message = response.json().get("message", {})
        dates = message.get("published-print") or message.get("published-online") or message.get("published") or {}
        parts = dates.get("date-parts", [[]])[0]
        fields: dict[str, object] = {}
        if message.get("title"):
            fields["title"] = str(message["title"][0]).strip()
        if message.get("author"):
            fields["authors"] = tuple(" ".join(filter(None, (item.get("given"), item.get("family")))).strip() for item in message["author"] if item.get("given") or item.get("family"))
        if message.get("container-title"):
            fields["journal"] = str(message["container-title"][0]).strip()
        if parts:
            fields["year"] = int(parts[0])
        fields["doi"] = str(message.get("DOI", doi)).strip().lower()
        return fields
    except Exception:
        return {}


def _enrich_from_doi(doi: str, title: str | None, warnings: list[str]) -> dict[str, ExtractedField]:
    bibtex, crossref = _fetch_doi_bibtex(doi), _fetch_crossref_work(doi)
    if not bibtex and not crossref:
        warnings.append("doi_metadata_unavailable")
        return {}
    result: dict[str, ExtractedField] = {}
    values: dict[str, list[tuple[object, str]]] = {}
    for source, payload in (("doi_bibtex", bibtex), ("doi_crossref", crossref)):
        for key, value in payload.items():
            field = "authors" if key == "author" else key
            values.setdefault(field, []).append((value, source))
    for field, candidates in values.items():
        chosen, source = candidates[-1]
        if len(candidates) > 1 and _title_key(str(candidates[0][0])) != _title_key(str(candidates[-1][0])):
            warnings.append("doi_metadata_conflict")
        if field == "doi":
            continue
        if field == "title" and title and _title_key(str(chosen)) != _title_key(title):
            continue
        result[field] = ExtractedField(value=chosen, source=source, confidence="high")
    return result


def _doi_title_matches(doi: str, title: str) -> bool | None:
    """Return None when lookup is unavailable, otherwise compare normalized titles."""
    remote_title = _lookup_doi_title(doi)
    if not remote_title or not title:
        return None
    local, remote = _title_key(title), _title_key(remote_title)
    return local == remote or local in remote or remote in local or SequenceMatcher(None, local, remote).ratio() >= 0.82


def extract_metadata(data: bytes) -> ExtractedMetadata:
    """Extract metadata from a PDF byte buffer. Never raises on valid PDF."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        page_count = len(reader.pages)
    except Exception:
        return ExtractedMetadata(warnings=("invalid_pdf",))

    warnings = []

    title = None
    authors = None
    year = None
    journal = None

    try:
        meta = reader.metadata
        if meta:
            if meta.title:
                t = str(meta.title).strip()
                if t:
                    confidence = 'medium' if len(t) > 5 else 'low'
                    title = ExtractedField(value=t, source='pdf_info', confidence=confidence)

            if meta.author:
                a = str(meta.author).strip()
                if a:
                    parts = re.split(r';|,|\s+and\s+', a, flags=re.IGNORECASE)
                    parsed_authors = tuple(p.strip() for p in parts if p.strip())
                    if parsed_authors:
                        authors = ExtractedField(value=parsed_authors, source='pdf_info', confidence='medium')

            for date_key in ('/CreationDate', '/ModDate'):
                date_val = meta.get(date_key)
                if date_val:
                    match = re.search(r'(?:D:)?((?:19|20)\d{2})', str(date_val))
                    if match:
                        year = ExtractedField(value=int(match.group(1)), source='pdf_file_date', confidence='low')
                        warnings.append('file_date_is_not_publication_date')
                        break
    except Exception:
        pass

    first_page_text = ""
    combined_text = ""

    selected_pages = _selected_pages(page_count)
    page_texts: dict[int, str] = {}
    for i in selected_pages:
        try:
            page = reader.pages[i]
            text = (page.extract_text() or '')[:30000]
            if text:
                page_texts[i] = text
                if i == selected_pages[0]:
                    first_page_text = text
                combined_text += text + "\n"
        except Exception:
            pass

    doi = None
    arxiv_id = None

    # OCR is only used when the selectable text cannot supply useful metadata.
    if len(combined_text) < 100 or not _DOI_RE.search(combined_text):
        ocr_text = _ocr_text(data, selected_pages)
        if ocr_text:
            combined_text += "\n" + ocr_text
            if not first_page_text:
                first_page_text = ocr_text
            warnings.append('ocr_used')

    if not title and first_page_text:
        lines = first_page_text.splitlines()
        candidate_lines = [line.strip() for line in lines[:10]]
        valid_lines = [line for line in candidate_lines if 10 < len(line) < 200]
        if valid_lines:
            longest_line = max(valid_lines, key=len)
            title = ExtractedField(value=longest_line, source='first_page', confidence='low')

    if combined_text or data:
        candidates: list[tuple[str, str, int | None]] = []
        for page, text in page_texts.items():
            candidates.extend((match.group(1), 'pdf_page', page + 1) for match in _DOI_RE.finditer(text))
        candidates.extend((match.group(1), 'pdf_page', None) for match in _DOI_RE.finditer(combined_text) if match.group(1) not in {item[0] for item in candidates})
        candidates.extend((match.group(1), 'pdf_raw', None) for match in _DOI_RE.finditer(data.decode('latin-1', errors='ignore')))

        normalized_candidates: list[tuple[str, str, int | None]] = []
        seen: set[str] = set()
        for raw, source, page in candidates:
            value = re.sub(r"\s+", "", raw.lower()).rstrip('.,;')
            while value.endswith(')') and value.count(')') > value.count('('):
                value = value[:-1]
            normalized = normalize_identifier(value, 'doi')
            if normalized and normalized not in seen:
                seen.add(normalized)
                normalized_candidates.append((normalized, source, page))

        title_value = title.value if title else None
        matches = [(item, _doi_title_matches(item[0], title_value)) for item in normalized_candidates]
        accepted = next((item for item, matched in matches if matched is True), None)
        if accepted is None and matches:
            accepted = next((item for item, matched in matches if matched is None), None)
        if accepted:
            normalized_doi, source, page = accepted
            matched = next(matched for item, matched in matches if item == accepted)
            doi = ExtractedField(value=normalized_doi, source='doi_lookup' if matched is True else source, confidence='high' if matched is True else 'low', page=page)
            warnings.append('identifier_requires_review')
            if matched is None:
                warnings.append('doi_unverified')
            enriched = _enrich_from_doi(normalized_doi, title.value if title else None, warnings)
            if title is None and enriched.get('title'):
                title = enriched['title']
            if authors is None and enriched.get('authors'):
                authors = enriched['authors']
            if enriched.get('year'):
                year = enriched['year']
            if enriched.get('journal'):
                journal = enriched['journal']
        if any(matched is False for _, matched in matches) and not doi:
            warnings.append('doi_title_mismatch')
        if len(normalized_candidates) > 1:
            warnings.append('multiple_doi_candidates')

        arxiv_match = _ARXIV_RE.search(combined_text)
        if arxiv_match:
            arxiv_id = ExtractedField(value=normalize_identifier(arxiv_match.group(1), 'arxiv'), source='text_scan', confidence='high')

    if not year and first_page_text:
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', first_page_text)
        if year_match:
            year = ExtractedField(value=int(year_match.group(1)), source='first_page', confidence='low')

    if len(combined_text) < 100:
        warnings.append('short_text')
    if not title:
        warnings.append('missing_title')
    if not doi:
        warnings.append('missing_doi')
    if not authors:
        warnings.append('missing_authors')

    return ExtractedMetadata(
        title=title,
        doi=doi,
        arxiv_id=arxiv_id,
        authors=authors,
        year=year,
        journal=journal,
        page_count=page_count,
        warnings=tuple(warnings)
    )
