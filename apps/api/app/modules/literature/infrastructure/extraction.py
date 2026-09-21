"""PDF metadata extraction without OCR or external AI."""

import io
import re
from app.modules.literature.domain.workflow import ExtractedField, ExtractedMetadata
from app.modules.literature.domain.canonical import normalize_identifier

import pypdf


_DOI_RE = re.compile(r'\b(10\.\d{4,9}/[^\s]+)', re.IGNORECASE)
_ARXIV_RE = re.compile(r'(?:arxiv[:\s]*)(\d{4}\.\d{4,5}(?:v\d+)?)', re.IGNORECASE)


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

    for i in range(min(3, page_count)):
        try:
            page = reader.pages[i]
            text = (page.extract_text() or '')[:30000]
            if text:
                if i == 0:
                    first_page_text = text
                combined_text += text + "\n"
        except Exception:
            pass

    doi = None
    arxiv_id = None

    if combined_text:
        doi_match = _DOI_RE.search(combined_text)
        if doi_match:
            raw_doi = doi_match.group(1).lower()
            raw_doi = raw_doi.rstrip('.,;')
            while raw_doi.endswith(')') and raw_doi.count(')') > raw_doi.count('('):
                raw_doi = raw_doi[:-1]
            doi = ExtractedField(value=normalize_identifier(raw_doi, 'doi'), source='text_scan', confidence='low')
            warnings.append('identifier_requires_review')
            if len(set(_DOI_RE.findall(combined_text))) > 1:
                warnings.append('multiple_doi_candidates')

        arxiv_match = _ARXIV_RE.search(combined_text)
        if arxiv_match:
            arxiv_id = ExtractedField(value=normalize_identifier(arxiv_match.group(1), 'arxiv'), source='text_scan', confidence='high')

    if not title and first_page_text:
        lines = first_page_text.splitlines()
        candidate_lines = [line.strip() for line in lines[:10]]
        valid_lines = [line for line in candidate_lines if 10 < len(line) < 200]
        if valid_lines:
            longest_line = max(valid_lines, key=len)
            title = ExtractedField(value=longest_line, source='first_page', confidence='low')

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
        page_count=page_count,
        warnings=tuple(warnings)
    )
