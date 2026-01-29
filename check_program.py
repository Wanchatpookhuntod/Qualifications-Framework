from app import app, db
from models import Program, Course, User, Section

with app.app_context():
    p = Program.query.filter_by(name='Computer Science').first()
    if not p:
        print("Program 'Computer Science' not found.")
    else:
        print(f"Program: {p.name} (ID: {p.id})")
        courses = Course.query.filter_by(program_id=p.id).all()
        print(f"Associated Courses: {len(courses)}")
        users = User.query.filter_by(program_id=p.id).all()
        print(f"Associated Users: {len(users)}")
        
        # Check if any course in this program has sections
        has_sections = False
        for c in courses:
            if Section.query.filter_by(course_id=c.id).first():
                has_sections = True
                break
        print(f"Has Sections (Open Courses): {has_sections}")
