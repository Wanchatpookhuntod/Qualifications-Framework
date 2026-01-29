import json
from app import app, db
from models import Faculty, Program, Course

def seed_multimedia():
    with open('multimedia_curriculum.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    with app.app_context():
        # 1. Faculty
        prog_info = data.get('curriculum_info', {})
        faculty_name = prog_info.get('faculty') or "คณะวิทยาศาสตร์และเทคโนโลยี"
        faculty = Faculty.query.filter_by(name=faculty_name).first()
        if not faculty:
            faculty = Faculty(name=faculty_name)
            db.session.add(faculty)
            db.session.commit()
            print(f"Created Faculty: {faculty_name}")

        # 2. Program
        curriculum_name_th = prog_info.get('name') or ""
        program_name = "เทคโนโลยีมัลติมีเดีย"
        if "สาขาวิชา" in curriculum_name_th:
            program_name = curriculum_name_th.split("สาขาวิชา", 1)[1].strip() or program_name
        program = Program.query.filter_by(name=program_name, faculty_id=faculty.id).first()
        if not program:
            # revision_year is "พ.ศ. 2569", extract numeric part
            revision_year = prog_info.get('revision_year', '').strip()
            year_str = revision_year.replace("พ.ศ. ", "").strip() if revision_year else ""
            year = int(year_str)
            program = Program(name=program_name, faculty_id=faculty.id, year=year)
            db.session.add(program)
            db.session.commit()
            print(f"Created Program: {program_name} ({year})")

        # 3. Courses
        course_descriptions = data.get('course_descriptions', {})
        courses_catalog = data.get('courses', {})

        def build_course_meta_map(node):
            """Flatten course_descriptions into {code: {name_en, description, ...}}.

            Supports both the current lean schema (name_en/description only) and older
            schemas that may include name_th/credits, while keeping curriculum_structure
            as the canonical source for code/name_th/credits.
            """
            meta_map = {}
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(value, dict) and (
                        'name_en' in value or 'description' in value or 'name_th' in value or 'credits' in value
                    ):
                        meta_map[key] = value
                    else:
                        meta_map.update(build_course_meta_map(value))
            elif isinstance(node, list):
                for item in node:
                    meta_map.update(build_course_meta_map(item))
            return meta_map

        # Prefer the new schema's top-level course catalog when present.
        if isinstance(courses_catalog, dict) and courses_catalog:
            course_meta = courses_catalog
        else:
            course_meta = build_course_meta_map(course_descriptions)

        def upsert_course(code, name_th, credits, meta):
            name_en = (meta.get('name_en') or '').strip() or name_th
            desc_text = (meta.get('description') or '').strip()

            existing_course = Course.query.filter_by(code=code, program_id=program.id).first()
            if existing_course:
                existing_course.name_th = name_th
                existing_course.name_en = name_en
                existing_course.credits = credits
                existing_course.description = desc_text
                existing_course.program_id = program.id
                print(f"Updated Course: {code} - {name_th}")
            else:
                new_course = Course(
                    code=code,
                    name_th=name_th,
                    name_en=name_en,
                    credits=credits,
                    description=desc_text,
                    program_id=program.id
                )
                db.session.add(new_course)
                print(f"Created Course: {code} - {name_th}")

        def process_group(group_data):
            # Old schema: explicit course objects
            if 'courses' in group_data and isinstance(group_data.get('courses'), list):
                for c in group_data.get('courses', []):
                    code = c['code']
                    name_th = c['name']
                    credits = c.get('credits')
                    meta = course_meta.get(code, {}) if isinstance(course_meta, dict) else {}
                    upsert_course(code, name_th, credits, meta if isinstance(meta, dict) else {})
                return

            # New schema: list of course codes
            if 'course_codes' in group_data and isinstance(group_data.get('course_codes'), list):
                for code in group_data.get('course_codes', []):
                    if not isinstance(code, str) or not code.strip():
                        continue
                    code = code.strip()
                    meta = course_meta.get(code, {}) if isinstance(course_meta, dict) else {}
                    if not isinstance(meta, dict):
                        meta = {}
                    name_th = meta.get('name') or code
                    credits = meta.get('credits')
                    upsert_course(code, name_th, credits, meta)
                return

        # Process structure
        structure = data.get('curriculum_structure', {})
        
        # General Education
        gen_ed = structure.get('general_education', {})
        for _, g_data in gen_ed.get('groups', {}).items():
            process_group(g_data)
            
        # Specialized Courses
        spec_courses = structure.get('specialized_courses', {})
        for _, g_data in spec_courses.get('groups', {}).items():
            if 'courses' in g_data:
                process_group(g_data)
            elif 'plans' in g_data:
                for plan_id, plan_data in g_data['plans'].items():
                    process_group(plan_data)
            elif 'course_codes' in g_data:
                process_group(g_data)

        # Minor Program
        minor = structure.get('minor_program', {})
        if 'courses' in minor:
            process_group(minor)

        db.session.commit()
        print("Database seeding from multimedia_curriculum.json complete!")

if __name__ == '__main__':
    seed_multimedia()
