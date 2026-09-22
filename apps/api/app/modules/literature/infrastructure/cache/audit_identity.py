"""Read-only Literature identity audit; never initializes or repairs a database."""

import argparse
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from app.modules.literature.domain.canonical import identifiers, normalize_identifier
from app.modules.literature.domain.models import Paper


_IDENTITY_TABLES = {
    "literature_documents", "literature_identifiers", "literature_paper_aliases",
    "literature_source_references", "literature_origins", "literature_identity_conflicts",
}


def audit_identity(database: str | Path) -> dict:
    path = Path(database).resolve()
    # mode=ro also prevents a typo from creating a new empty database.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {
            name: connection.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
            for name in sorted(tables) if name.startswith("literature_")
        }
        report = {
            "read_only": True,
            "scientific_verification": False,
            "counts": counts,
            "missing_tables": sorted(_IDENTITY_TABLES - tables),
            "issues": [],
        }
        if report["missing_tables"]:
            return {**report, "status": "canonical_schema_missing"}

        issues = report["issues"]
        documents = {row["id"]: row["metadata_json"] for row in connection.execute("SELECT id,metadata_json FROM literature_documents ORDER BY id")}
        indexed = {(row["kind"], row["value"]): row["paper_id"] for row in connection.execute("SELECT * FROM literature_identifiers ORDER BY kind,value")}
        report["identifier_kinds"] = dict(sorted(Counter(kind for kind, _ in indexed).items()))
        report["documents_without_indexed_identifiers"] = sorted(set(documents) - set(indexed.values()))
        for paper_id, payload in documents.items():
            try:
                metadata = json.loads(payload)
                if metadata.get("id") != paper_id:
                    issues.append({"code": "metadata_id_mismatch", "paper_id": paper_id})
                expected = identifiers(Paper(paper_id, "", doi=metadata.get("doi"), arxiv_id=metadata.get("arxiv_id"), openalex_id=metadata.get("openalex_id")))
            except (ValueError, TypeError, AttributeError):
                issues.append({"code": "invalid_metadata_identity", "paper_id": paper_id})
                continue
            for kind, value in expected.items():
                owner = indexed.get((kind, value))
                if owner != paper_id:
                    issues.append({"code": "identifier_owner_mismatch" if owner else "identifier_not_indexed", "paper_id": paper_id, "kind": kind, "indexed_owner": owner})
        for (kind, value), owner in indexed.items():
            if owner not in documents:
                issues.append({"code": "orphan_identifier", "paper_id": owner, "kind": kind})
            try:
                if kind not in {"doi", "arxiv", "openalex"}:
                    raise ValueError("Unknown identifier kind")
                if normalize_identifier(value, kind) != value:
                    issues.append({"code": "unnormalized_identifier", "paper_id": owner, "kind": kind})
            except (ValueError, TypeError, KeyError, AttributeError):
                issues.append({"code": "invalid_indexed_identifier", "paper_id": owner, "kind": kind})

        # Additional historical identifiers (e.g. preprint DOI) are valid retained evidence.
        # Do not treat all values absent from current metadata as errors or delete them.
        report["alias_reasons"] = dict(sorted(Counter(row[0] for row in connection.execute("SELECT reason FROM literature_paper_aliases")).items()))
        report["weak_aliases"] = []
        for row in connection.execute("SELECT * FROM literature_paper_aliases ORDER BY alias"):
            if "title" in row["reason"].casefold():
                report["weak_aliases"].append({"alias": row["alias"], "paper_id": row["paper_id"], "reason": row["reason"][:160]})
        for table in ("literature_paper_aliases", "literature_source_references", "literature_origins"):
            for row in connection.execute(f"SELECT paper_id FROM {table} ORDER BY paper_id"):
                if row[0] not in documents:
                    issues.append({"code": "orphan_ownership", "table": table, "paper_id": row[0]})
        report["unresolved_records"] = [
            {"id": row["id"], "legacy_id": row["legacy_id"], "reason": row["reason"][:160]}
            for row in connection.execute("SELECT id,legacy_id,reason FROM literature_identity_conflicts ORDER BY id")
        ]
        report["status"] = "needs_review" if issues or report["weak_aliases"] or report["unresolved_records"] else "no_detected_identity_issues"
        return report


def main():
    from app.core.config import settings

    parser = argparse.ArgumentParser(description="Read-only Literature identity audit (no scientific verification or repair)")
    parser.add_argument("--database", default=settings.database_url.removeprefix("sqlite:///"))
    args = parser.parse_args()
    try:
        report = audit_identity(args.database)
    except sqlite3.Error:
        parser.error("Unable to read the existing SQLite database and expected Literature schema")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
