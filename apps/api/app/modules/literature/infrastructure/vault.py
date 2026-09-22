"""Read-only inventory and explicit copy/verify relocation of referenced Vault assets."""

import argparse
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from app.modules.literature.application.errors import LocalAssetError
from app.modules.literature.infrastructure.cache.canonical import _attachment
from app.modules.literature.infrastructure.files import LocalLiteratureFiles


def _manifest(database):
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as c:
        c.execute("PRAGMA query_only = ON")
        c.execute("BEGIN")
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "literature_assets" not in tables:
            return None, 0
        rows = c.execute("SELECT id,payload_json,active FROM literature_assets ORDER BY id").fetchall()
        pending = c.execute("SELECT COUNT(*) FROM literature_upload_items WHERE status NOT IN ('confirmed','cancelled')").fetchone()[0] if "literature_upload_items" in tables else 0
        return rows, pending


def _inspect(rows, files):
    results = []
    for asset_id, payload, active in rows:
        try:
            asset = _attachment(json.loads(payload))
            result = asdict(files.inspect(asset))
            result.update(storage_kind=asset.storage_kind, storage_key=asset.storage_key)
        except (ValueError, TypeError, KeyError):
            result = {"asset_id": asset_id, "state": "invalid", "storage_kind": "unknown"}
        results.append({**result, "asset_id": asset_id, "active": bool(active)})
    return results


def inspect_vault(database, root, *, copy_to=None, apply=False):
    if apply and copy_to is None:
        raise ValueError("Apply requires an explicit destination")
    files = LocalLiteratureFiles(str(root))
    rows, pending = _manifest(database)
    if rows is None:
        return {"status": "canonical_schema_missing", "read_only": True, "items": []}
    items = _inspect(rows, files)
    report = {
        "status": "inspected", "read_only": not apply,
        "pending_uploads": pending,
        "counts": dict(sorted(Counter(item["state"] for item in items).items())),
        "items": items,
    }
    if copy_to is None:
        return report
    destination = LocalLiteratureFiles(str(copy_to))
    if destination.root.is_relative_to(files.root) or files.root.is_relative_to(destination.root):
        raise ValueError("Source and destination must be separate non-overlapping Vault roots")
    blocked = pending > 0 or any(item["state"] not in {"verified", "remote_only"} for item in items)
    report.update(status="blocked" if blocked else "planned", ready_to_switch=False, copies=[])
    if blocked or not apply:
        return report
    for asset_id, payload, _ in rows:
        asset = _attachment(json.loads(payload))
        if asset.storage_kind != "local":
            continue
        try:
            previous = destination.inspect(asset)
            if previous.state == "verified":
                outcome = "already_verified"
            elif previous.state != "missing":
                raise LocalAssetError(previous.state)
            else:
                opened = files.open(asset)
                try:
                    data = b"".join(opened.chunks)
                finally:
                    if opened.close:
                        opened.close()
                if sha256(data).hexdigest() != asset.storage_key[:-4]:
                    raise LocalAssetError("corrupt")
                key, digest = destination.store_pdf(data, asset.filename)
                if key != asset.storage_key or digest != asset.storage_key[:-4] or destination.inspect(asset).state != "verified":
                    raise LocalAssetError("corrupt")
                outcome = "copied_verified"
            report["copies"].append({"asset_id": asset_id, "status": outcome})
        except (LocalAssetError, OSError, ValueError) as error:
            report["copies"].append({"asset_id": asset_id, "status": "failed", "reason": error.state if isinstance(error, LocalAssetError) else "copy_failed"})
    # Recheck the manifest and destination before telling an operator it is ready.
    current, current_pending = _manifest(database)
    stable = current == rows and not current_pending
    verified = all(item["state"] in {"verified", "remote_only"} for item in _inspect(rows, destination))
    succeeded = all(item["status"] != "failed" for item in report["copies"])
    report["ready_to_switch"] = stable and verified and succeeded
    report["status"] = "copied_verified" if report["ready_to_switch"] else "incomplete"
    return report


def main():
    from app.core.config import settings

    parser = argparse.ArgumentParser(description="Inventory Literature assets; optionally copy/verify a quiesced Vault without deleting or changing configuration")
    parser.add_argument("--database", default=settings.database_url.removeprefix("sqlite:///"))
    parser.add_argument("--root", default=settings.literature_vault_root or None)
    parser.add_argument("--copy-to")
    parser.add_argument("--apply", action="store_true", help="Copy verified owned assets; default is read-only")
    args = parser.parse_args()
    root = args.root or Path(args.database).parent / "literature-assets"
    try:
        report = inspect_vault(args.database, root, copy_to=args.copy_to, apply=args.apply)
    except (ValueError, sqlite3.Error, OSError):
        parser.error("Check database/schema, separate Vault roots, destination permissions and explicit copy/apply options")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] in {"blocked", "incomplete", "canonical_schema_missing"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
