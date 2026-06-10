"""Seed CourseCLOs for หลักสูตรเทคโนโลยีมัลติมีเดีย 2569 from the official
CLO–PLO mapping document (เล่มหลักสูตร 2569).

Source: CLO/CLO_PLO_Mapping_วิชาเฉพาะ_หลักสูตรมัลติมีเดีย_2569.docx
Tables: รหัสวิชา | รายวิชา | CLO | PLO ที่รับผิดชอบ — course code appears only on
the first CLO row of each course; subsequent rows leave it blank.

Usage:
    python seed_clos_2569_official.py          # dry-run (default)
    python seed_clos_2569_official.py --yes    # apply

Requires authorized_user ADC at:
~/.config/gcloud/legacy_credentials/wanchatpookhuntod@gmail.com/adc.json
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

from docx import Document
from google.cloud import firestore as gcp_firestore
from google.oauth2.credentials import Credentials

ADC_PATH = os.path.expanduser(
    "~/.config/gcloud/legacy_credentials/wanchatpookhuntod@gmail.com/adc.json"
)
PROJECT_ID = "qualificationsframework"
PROGRAM_ID_2569 = "TM0hoBhA2Zc3iP16KGHs"  # วท.บ. เทคโนโลยีมัลติมีเดีย (2569)
DOCX_PATH = "CLO/CLO_PLO_Mapping_วิชาเฉพาะ_หลักสูตรมัลติมีเดีย_2569.docx"
VALID_PLOS = {"PLO1", "PLO2", "PLO3", "PLO4", "PLO5"}

_CLO_RE = re.compile(r"^CLO\s*(\d+)\s*[:.)\-]?\s*(.*)$", re.DOTALL)


def parse_docx(path: str) -> dict:
    """Return {course_code: [{code, description, plo_codes, order}, ...]}."""
    doc = Document(path)
    by_course: dict = {}
    current = None
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) < 4 or cells[2] in ("", "CLO"):
                continue
            code_cell, _name, clo_cell, plo_cell = cells[0], cells[1], cells[2], cells[3]
            if code_cell:
                current = re.sub(r"\s+", " ", code_cell)
                by_course.setdefault(current, [])
            if not current:
                continue
            m = _CLO_RE.match(re.sub(r"\s+", " ", clo_cell))
            if not m:
                continue
            number = int(m.group(1))
            desc = m.group(2).strip()
            plos = [p.strip() for p in re.split(r"[,/]| และ ", plo_cell) if p.strip()]
            bad = [p for p in plos if p not in VALID_PLOS]
            if bad:
                print(f"  !! unknown PLO code(s) {bad} on {current} CLO{number}")
            by_course[current].append({
                "code": f"CLO{number}",
                "description": desc,
                "plo_codes": ",".join(p for p in plos if p in VALID_PLOS),
                "order": number,
            })
    return by_course


def main() -> None:
    apply_changes = "--yes" in sys.argv

    by_course = parse_docx(DOCX_PATH)
    total_clos = sum(len(v) for v in by_course.values())
    print(f"parsed {len(by_course)} courses, {total_clos} CLOs from docx\n")

    creds = Credentials.from_authorized_user_info(json.load(open(ADC_PATH)))
    db = gcp_firestore.Client(project=PROJECT_ID, credentials=creds)

    courses_by_code = {}
    for d in db.collection("courses").where("program_id", "==", PROGRAM_ID_2569).stream():
        c = d.to_dict() or {}
        courses_by_code[re.sub(r"\s+", " ", (c.get("code") or "").strip())] = (d.id, c)

    existing_clo_courses = {
        (d.to_dict() or {}).get("course_id")
        for d in db.collection("course_clos").where("program_id", "==", PROGRAM_ID_2569).stream()
    }

    created = skipped = missing = 0
    for code, clos in sorted(by_course.items()):
        hit = courses_by_code.get(code)
        if not hit:
            missing += 1
            print(f"NOT IN 2569 PROGRAM: {code} ({len(clos)} CLOs) — skipped")
            continue
        cid, cdata = hit
        if cid in existing_clo_courses:
            skipped += len(clos)
            print(f"already has CLOs:    {code} {cdata.get('name_th','')[:35]} — skipped")
            continue
        print(f"{code} {cdata.get('name_th','')[:40]} -> {len(clos)} CLOs")
        for clo in clos:
            print(f"    {clo['code']}: {clo['description'][:55]}  [{clo['plo_codes']}]")
            if apply_changes:
                db.collection("course_clos").add({
                    "course_id": cid,
                    "program_id": PROGRAM_ID_2569,
                    "code": clo["code"],
                    "description": clo["description"],
                    "plo_codes": clo["plo_codes"],
                    "order": clo["order"],
                    "created_at": datetime.now(timezone.utc),
                })
            created += 1

    verb = "created" if apply_changes else "would create (dry-run; pass --yes to apply)"
    print(f"\n{created} CLOs {verb}; skipped(existing)={skipped}, courses not in program={missing}")


if __name__ == "__main__":
    main()
