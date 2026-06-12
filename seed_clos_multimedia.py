"""Seed CLOs for หลักสูตร วท.บ. เทคโนโลยีมัลติมีเดีย 2565 from docx file."""
import re
import sys
import os

os.environ.setdefault("FLASK_APP", "app")
sys.path.insert(0, os.path.dirname(__file__))

from docx import Document
from models import Program, Course, CourseCLO

DOCX_PATH = "CLO/clo_วท_เทคโนโลยีมัลติมีเดีย.docx"
PLO_HEADERS = ["PLO1", "PLO2", "PLO3", "PLO4", "PLO5", "PLO6", "PLO7", "PLO8"]
PROGRAM_KEYWORD = "มัลติมีเดีย"
PROGRAM_YEAR = 2565


def parse_docx(path):
    doc = Document(path)
    table = doc.tables[0]
    rows_out = []
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        clo_col = cells[2]
        if not clo_col.startswith("CLO"):
            continue
        code = cells[0].strip()
        desc = cells[3].strip()
        m = re.search(r"\d+", clo_col)
        number = int(m.group()) if m else None
        plos = []
        for idx, cell in enumerate(row.cells[4:], 0):
            if idx >= len(PLO_HEADERS):
                break
            if "<w:sym" in cell._tc.xml:
                plos.append(PLO_HEADERS[idx])
        rows_out.append((code, number, desc, ",".join(plos)))
    return rows_out


def find_program():
    programs = Program.find_all()
    matches = [
        p for p in programs
        if PROGRAM_KEYWORD in (p.name or "") and p.year == PROGRAM_YEAR
    ]
    if not matches:
        # fallback: just keyword
        matches = [p for p in programs if PROGRAM_KEYWORD in (p.name or "")]
    return matches


def normalize_code(code: str) -> str:
    return code.replace(" ", "").upper()


def main():
    clo_rows = parse_docx(DOCX_PATH)
    print(f"Parsed {len(clo_rows)} CLO rows from docx")

    programs = find_program()
    if not programs:
        print("ERROR: ไม่พบหลักสูตรเทคโนโลยีมัลติมีเดีย")
        return

    print(f"Found {len(programs)} matching program(s):")
    for p in programs:
        print(f"  [{p.id}] {p.name} {p.year}")

    if len(programs) > 1:
        print("ใช้ program แรก – แก้ไข script ถ้าต้องการ program อื่น")
    program = programs[0]

    courses = Course.find_by("program_id", program.id)
    course_map = {normalize_code(c.code or ""): c for c in courses if c.code}
    print(f"Found {len(courses)} courses in program")

    # group clo_rows by course code
    from collections import defaultdict
    by_course = defaultdict(list)
    for (code, number, desc, plos) in clo_rows:
        by_course[normalize_code(code)].append((number, desc, plos))

    inserted = 0
    skipped_course = []
    for norm_code, clo_list in by_course.items():
        course = course_map.get(norm_code)
        if not course:
            skipped_course.append(norm_code)
            continue

        # delete existing CLOs for this course first
        existing = CourseCLO.find_by("course_id", course.id)
        for e in existing:
            e.delete()

        for (number, desc, plos) in clo_list:
            CourseCLO(
                course_id=course.id,
                code=f"CLO{number}" if number else "CLO?",
                description=desc,
                plo_codes=plos,
                order=number,
            ).save()
            inserted += 1

    print(f"\nInserted {inserted} CLOs")
    if skipped_course:
        print(f"Skipped (course not found in program): {skipped_course}")


if __name__ == "__main__":
    main()
