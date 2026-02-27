from __future__ import annotations

from models import Course, Program


def main() -> None:
    programs = Program.find_by("name", "เทคโนโลยีมัลติมีเดีย")
    p = programs[0] if programs else None
    if not p:
        print("Program not found")
        return

    courses = Course.find_by("program_id", p.id)
    print(f"Program: {p.name} ({p.year})")
    print(f"Total courses found: {len(courses)}")
    for c in courses[:10]:
        print(f"- {c.code}: {c.name_th}")


if __name__ == "__main__":
    main()
