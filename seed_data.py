from __future__ import annotations

from models import Course, Faculty, Program, Section, Term, User


def seed_hierarchy() -> tuple[Faculty, Program]:
    """Create Faculty and Program hierarchy."""
    faculty_name = "Faculty of Engineering"
    program_name = "Computer Science"

    faculty = Faculty.first_by("name", faculty_name)
    if not faculty:
        faculty = Faculty(name=faculty_name).save()
        print(f"Created Faculty: {faculty_name}")

    programs = Program.find_by("name", program_name)
    program = next((p for p in programs if p.faculty_id == faculty.id), None)
    if not program:
        program = Program(name=program_name, faculty_id=faculty.id, year=2565).save()
        print(f"Created Program: {program_name}")

    return faculty, program


def seed_users(faculty: Faculty, program: Program) -> None:
    """Create default users for testing."""
    users = [
        {
            "username": "admin",
            "roles": ["admin"],
            "full_name": "System Administrator",
            "pass": "password",
            "faculty": None,
            "program": None,
        },
        {
            "username": "instructor1",
            "roles": ["instructor"],
            "full_name": "อาจารย์ สมชาย ใจดี",
            "pass": "pass123",
            "faculty": faculty,
            "program": program,
        },
        {
            "username": "head1",
            "roles": ["head"],
            "full_name": "หัวหน้าภาค สมศรี มั่งมี",
            "pass": "head123",
            "faculty": faculty,
            "program": program,
        },
        {
            "username": "academic1",
            "roles": ["academic"],
            "full_name": "ฝ่ายวิชาการ ใจดี",
            "pass": "academic123",
            "faculty": faculty,
            "program": None,
        },
    ]

    for u_data in users:
        if User.get_by_username(u_data["username"]):
            continue

        u = User(
            username=u_data["username"],
            roles=u_data["roles"],
            full_name=u_data["full_name"],
            faculty_id=(u_data["faculty"].id if u_data["faculty"] else None),
            program_id=(u_data["program"].id if u_data["program"] else None),
        )
        u.set_password(u_data["pass"])
        u.save()
        print(f"Created user: {u.username} ({','.join(u.roles)})")


def seed_sample_data(program: Program) -> None:
    """Create sample course and section data."""
    existing = [c for c in Course.find_by("code", "CS101") if c.program_id == program.id]
    if existing:
        course = existing[0]
    else:
        course = Course(
            code="CS101",
            name_th="การเขียนโปรแกรมพื้นฐาน",
            name_en="Introduction to Programming",
            credits="3(2-2-5)",
            description="พื้นฐานการเขียนโปรแกรมคอมพิวเตอร์ ตรรกศาสตร์ ข้อมูล และโครงสร้างควบคุม",
            program_id=program.id,
        ).save()
        print("Created sample course: CS101")

    term = next((t for t in Term.find_by("year", 2567) if t.semester == 1), None)
    if not term:
        term = Term(year=2567, semester=1).save()
        print("Created term: 1/2567")

    instructor = User.get_by_username("instructor1")
    if not instructor:
        return

    existing_sections = [
        s
        for s in Section.find_by("course_id", course.id)
        if s.term_id == term.id and (s.section_number or "") == "1"
    ]
    if existing_sections:
        return

        Section(
            course_id=course.id,
            instructor_id=instructor.id,
            term_id=term.id,
            section_number="1",
            is_open=True,
            is_open_tqf5=True,
            status="active",
        ).save()
    print("Created section 1 for CS101 (Open for editing)")


if __name__ == "__main__":
    print("Starting Firestore seeding...")
    f, p = seed_hierarchy()
    seed_users(f, p)
    seed_sample_data(p)
    print("Seeding complete!")
