from __future__ import annotations

from models import Course, Program, Section, User


def main() -> None:
    programs = Program.find_by("name", "Computer Science")
    p = programs[0] if programs else None
    if not p:
        print("Program 'Computer Science' not found.")
        return

    print(f"Program: {p.name} (ID: {p.id})")
    courses = Course.find_by("program_id", p.id)
    users = User.find_by("program_id", p.id)
    print(f"Associated Courses: {len(courses)}")
    print(f"Associated Users: {len(users)}")

    has_sections = False
    for c in courses:
        if Section.find_by("course_id", c.id):
            has_sections = True
            break
    print(f"Has Sections (Open Courses): {has_sections}")


if __name__ == "__main__":
    main()
