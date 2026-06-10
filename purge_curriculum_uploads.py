from __future__ import annotations

import argparse
from datetime import datetime
from typing import Iterable, Optional, Tuple

from firestore_db import get_firestore_client

try:
    from google.cloud.firestore_v1.base_query import FieldFilter  # type: ignore
except Exception:
    FieldFilter = None  # type: ignore


def _parse_date(value: str) -> datetime:
    """Parse YYYY-MM-DD into a naive datetime (00:00:00)."""
    value = (value or "").strip()
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception as e:
        raise SystemExit(f"Invalid date '{value}'. Use YYYY-MM-DD") from e


def _iter_doc_refs(query) -> Iterable[Tuple[str, object]]:
    for snap in query.stream():
        yield snap.id, snap.reference


def _batch_delete(refs: Iterable[Tuple[str, object]], batch_size: int = 450) -> int:
    db = get_firestore_client()
    deleted = 0
    batch = db.batch()
    pending = 0

    for _doc_id, ref in refs:
        batch.delete(ref)
        pending += 1
        if pending >= batch_size:
            batch.commit()
            deleted += pending
            batch = db.batch()
            pending = 0

    if pending:
        batch.commit()
        deleted += pending

    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Purge documents from Firestore collection 'curriculum_uploads'. "
            "Defaults to dry-run; use --yes to actually delete."
        )
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete documents (without this flag, only prints what would happen).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Target all documents in curriculum_uploads.",
    )
    parser.add_argument(
        "--before",
        type=str,
        default=None,
        help="Only delete documents with uploaded_at < YYYY-MM-DD.",
    )
    parser.add_argument(
        "--program-id",
        type=str,
        default=None,
        help="Only delete documents matching program_id.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many sample doc IDs to print in dry-run.",
    )

    args = parser.parse_args()

    if not args.all and not args.before and not args.program_id:
        # Safe default: allow dry-run scanning, but refuse destructive mode.
        if args.yes:
            raise SystemExit("Refusing to delete without a selector. Use --all and/or --before/--program-id")

    db = get_firestore_client()
    col = db.collection("curriculum_uploads")

    query = col
    selector = []

    if args.program_id:
        if FieldFilter is not None:
            query = query.where(filter=FieldFilter("program_id", "==", args.program_id))
        else:
            query = query.where("program_id", "==", args.program_id)
        selector.append(f"program_id={args.program_id}")

    before_dt: Optional[datetime] = None
    if args.before:
        before_dt = _parse_date(args.before)
        if FieldFilter is not None:
            query = query.where(filter=FieldFilter("uploaded_at", "<", before_dt))
        else:
            query = query.where("uploaded_at", "<", before_dt)
        selector.append(f"uploaded_at<{args.before}")

    if args.all:
        selector.append("ALL")

    selector_text = ", ".join(selector) if selector else "(no selector)"

    # Dry-run: count + sample
    if not args.yes:
        print(f"[DRY-RUN] Selector: {selector_text}")
        count = 0
        samples = []
        for doc_id, _ref in _iter_doc_refs(query):
            count += 1
            if len(samples) < max(0, int(args.limit)):
                samples.append(doc_id)
            if count % 1000 == 0:
                print(f"  scanned: {count} docs...")

        print(f"Would delete: {count} docs from curriculum_uploads")
        if samples:
            print("Sample doc IDs:")
            for s in samples:
                print(f"  - {s}")
        else:
            print("No matching documents.")

        print("\nTo actually delete, re-run with: --yes")
        return

    # Destructive mode
    if args.all and (args.before or args.program_id):
        # --all doesn't change the query, but it can be confusing; keep it explicit.
        print(f"Deleting with selector: {selector_text} (note: --all is redundant with other selectors)")
    else:
        print(f"Deleting with selector: {selector_text}")

    deleted = _batch_delete(_iter_doc_refs(query))
    print(f"Deleted: {deleted} docs from curriculum_uploads")


if __name__ == "__main__":
    main()
