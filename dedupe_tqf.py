"""Remove duplicate TQF3/TQF5 documents that share the same section_id.

A section must have at most one TQF3 and one TQF5 document. A race in the
instructor "open document" flow could historically create duplicates, which
made the head dashboard and the instructor view disagree on status: they read
through different helpers (``find_in`` vs ``first_by``) that, with no
``order_by``, happened to land on different copies.

This script keeps the single authoritative copy per section
(``models.pick_canonical_tqf``: highest workflow status, then most recent
``submitted_at``, then greatest doc id) and deletes the rest. When a duplicate
TQF3 is removed, any surviving TQF5 still pointing at it via ``tqf3_id`` is
repointed to the surviving TQF3.

Dry-run by default; pass --apply to actually delete.

    python dedupe_tqf.py            # report only
    python dedupe_tqf.py --apply    # delete duplicates
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from models import TQF3, TQF5, pick_canonical_tqf


def _group_by_section(docs):
    groups = defaultdict(list)
    for doc in docs:
        if doc.section_id:
            groups[doc.section_id].append(doc)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate TQF3/TQF5 documents.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete duplicates and repoint references (default: dry-run).",
    )
    args = parser.parse_args()

    tqf3_docs = TQF3.find_all()
    tqf5_docs = TQF5.find_all()

    tqf3_groups = _group_by_section(tqf3_docs)
    tqf5_groups = _group_by_section(tqf5_docs)

    tqf3_keep: dict[str, str] = {}       # section_id -> surviving tqf3 id
    tqf3_remove: list[tuple[str, TQF3]] = []
    for sid, docs in tqf3_groups.items():
        canonical = pick_canonical_tqf(docs)
        tqf3_keep[sid] = canonical.id
        tqf3_remove.extend((sid, d) for d in docs if d.id != canonical.id)

    removed_tqf3_ids = {d.id for _, d in tqf3_remove}

    tqf5_remove: list[tuple[str, TQF5]] = []
    for sid, docs in tqf5_groups.items():
        canonical = pick_canonical_tqf(docs)
        tqf5_remove.extend((sid, d) for d in docs if d.id != canonical.id)

    removed_tqf5_ids = {d.id for _, d in tqf5_remove}

    # Surviving TQF5 docs whose tqf3_id points at a TQF3 we are about to delete.
    repoint: list[tuple[TQF5, str]] = []
    for doc in tqf5_docs:
        if doc.id in removed_tqf5_ids:
            continue
        if doc.tqf3_id and doc.tqf3_id in removed_tqf3_ids:
            new_id = tqf3_keep.get(doc.section_id)
            if new_id and new_id != doc.tqf3_id:
                repoint.append((doc, new_id))

    tqf3_dupe_sections = sum(1 for v in tqf3_groups.values() if len(v) > 1)
    tqf5_dupe_sections = sum(1 for v in tqf5_groups.values() if len(v) > 1)

    print(
        f"TQF3: {len(tqf3_docs)} docs, {tqf3_dupe_sections} section(s) with duplicates, "
        f"{len(tqf3_remove)} to delete"
    )
    for sid, d in tqf3_remove:
        print(f"  - delete tqf3 {d.id} (section={sid}, status={d.status}) -> keep {tqf3_keep[sid]}")
    print(
        f"TQF5: {len(tqf5_docs)} docs, {tqf5_dupe_sections} section(s) with duplicates, "
        f"{len(tqf5_remove)} to delete"
    )
    for sid, d in tqf5_remove:
        print(f"  - delete tqf5 {d.id} (section={sid}, status={d.status})")
    print(f"TQF5 tqf3_id repoints: {len(repoint)}")
    for d, new_id in repoint:
        print(f"  - tqf5 {d.id}: tqf3_id {d.tqf3_id} -> {new_id}")

    if not args.apply:
        print("\nDry-run. Re-run with --apply to delete.")
        return

    for _, d in tqf3_remove:
        d.delete()
    for _, d in tqf5_remove:
        d.delete()
    for d, new_id in repoint:
        d.tqf3_id = new_id
        d.save()
    print(f"\nApplied: deleted {len(tqf3_remove)} TQF3, {len(tqf5_remove)} TQF5; repointed {len(repoint)} TQF5.")


if __name__ == "__main__":
    main()
