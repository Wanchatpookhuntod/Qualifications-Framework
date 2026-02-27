from __future__ import annotations

import json
import os

from models import Course, Faculty, Program


def seed_multimedia() -> None:
    data_path = os.path.join(os.path.dirname(__file__), "multimedia_curriculum.json")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    prog_info = data.get("curriculum_info", {})

    faculty_name = prog_info.get("faculty") or "คณะวิทยาศาสตร์และเทคโนโลยี"
    faculty = Faculty.first_by("name", faculty_name)
    if not faculty:
        faculty = Faculty(name=faculty_name).save()
        print(f"Created Faculty: {faculty_name}")

    curriculum_name_th = prog_info.get("name") or ""
    program_name = "เทคโนโลยีมัลติมีเดีย"
    if "สาขาวิชา" in curriculum_name_th:
        program_name = curriculum_name_th.split("สาขาวิชา", 1)[1].strip() or program_name

    programs = Program.find_by("name", program_name)
    program = next((p for p in programs if p.faculty_id == faculty.id), None)
    if not program:
        revision_year = (prog_info.get("revision_year") or "").strip()
        year_str = revision_year.replace("พ.ศ. ", "").strip() if revision_year else ""
        year = int(year_str) if year_str.isdigit() else None
        program = Program(name=program_name, faculty_id=faculty.id, year=year).save()
        print(f"Created Program: {program_name} ({year})")

    course_descriptions = data.get("course_descriptions", {})
    courses_catalog = data.get("courses", {})

    def build_course_meta_map(node):
        meta_map = {}
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict) and (
                    "name_en" in value
                    or "description" in value
                    or "name_th" in value
                    or "credits" in value
                    or "name" in value
                ):
                    meta_map[key] = value
                else:
                    meta_map.update(build_course_meta_map(value))
        elif isinstance(node, list):
            for item in node:
                meta_map.update(build_course_meta_map(item))
        return meta_map

    if isinstance(courses_catalog, dict) and courses_catalog:
        course_meta = courses_catalog
    else:
        course_meta = build_course_meta_map(course_descriptions)

    created = 0
    updated = 0

    def upsert_course(code: str, name_th: str, credits: str | None, meta: dict) -> None:
        nonlocal created, updated
        name_en = (meta.get("name_en") or "").strip() or name_th
        desc_text = (meta.get("description") or "").strip()

        existing = [c for c in Course.find_by("code", code) if c.program_id == program.id]
        if existing:
            c = existing[0]
            c.name_th = name_th
            c.name_en = name_en
            c.credits = credits
            c.description = desc_text
            c.program_id = program.id
            c.save()
            updated += 1
            print(f"Updated Course: {code} - {name_th}")
            return

        Course(
            code=code,
            name_th=name_th,
            name_en=name_en,
            credits=credits,
            description=desc_text,
            program_id=program.id,
        ).save()
        created += 1
        print(f"Created Course: {code} - {name_th}")

    def process_group(group_data: dict) -> None:
        if "courses" in group_data and isinstance(group_data.get("courses"), list):
            for c in group_data.get("courses", []):
                code = c.get("code")
                name_th = c.get("name")
                if not code or not name_th:
                    continue
                credits = c.get("credits")
                meta = course_meta.get(code, {}) if isinstance(course_meta, dict) else {}
                upsert_course(code, name_th, credits, meta if isinstance(meta, dict) else {})
            return

        if "course_codes" in group_data and isinstance(group_data.get("course_codes"), list):
            for code in group_data.get("course_codes", []):
                if not isinstance(code, str) or not code.strip():
                    continue
                code = code.strip()
                meta = course_meta.get(code, {}) if isinstance(course_meta, dict) else {}
                if not isinstance(meta, dict):
                    meta = {}
                name_th = meta.get("name") or meta.get("name_th") or code
                credits = meta.get("credits")
                upsert_course(code, name_th, credits, meta)
            return

    structure = data.get("curriculum_structure", {})

    gen_ed = structure.get("general_education", {})
    for _, g_data in (gen_ed.get("groups", {}) or {}).items():
        if isinstance(g_data, dict):
            process_group(g_data)

    spec_courses = structure.get("specialized_courses", {})
    for _, g_data in (spec_courses.get("groups", {}) or {}).items():
        if not isinstance(g_data, dict):
            continue
        if "courses" in g_data or "course_codes" in g_data:
            process_group(g_data)
        elif "plans" in g_data and isinstance(g_data.get("plans"), dict):
            for _, plan_data in g_data["plans"].items():
                if isinstance(plan_data, dict):
                    process_group(plan_data)

    minor = structure.get("minor_program", {})
    if isinstance(minor, dict) and ("courses" in minor or "course_codes" in minor):
        process_group(minor)

    print(
        "Database seeding from multimedia_curriculum.json complete! "
        f"({created} created, {updated} updated)"
    )


if __name__ == "__main__":
    seed_multimedia()
