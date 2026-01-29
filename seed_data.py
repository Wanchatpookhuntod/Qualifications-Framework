from app import app, db
from models import User, Course, Term, Section, Faculty, Program

def seed_hierarchy():
    """Create Faculty and Program hierarchy."""
    f = Faculty.query.filter_by(name='Faculty of Engineering').first()
    if not f:
        f = Faculty(name='Faculty of Engineering')
        db.session.add(f)
        db.session.commit()
        print("Created Faculty: Engineering")
    
    p = Program.query.filter_by(name='Computer Science').first()
    if not p:
        p = Program(name='Computer Science', faculty_id=f.id, year=2565)
        db.session.add(p)
        db.session.commit()
        print("Created Program: Computer Science")
    return f, p

def seed_users(faculty, program):
    """Create default users for testing."""
    users = [
        {'username': 'admin', 'role': 'admin', 'full_name': 'System Administrator', 'pass': 'admin123', 'faculty': None, 'program': None},
        {'username': 'instructor1', 'role': 'instructor', 'full_name': 'อาจารย์ สมชาย ใจดี', 'pass': 'pass123', 'faculty': faculty, 'program': program},
        {'username': 'head1', 'role': 'head', 'full_name': 'หัวหน้าภาค สมศรี มั่งมี', 'pass': 'head123', 'faculty': faculty, 'program': program},
        {'username': 'academic1', 'role': 'academic', 'full_name': 'ฝ่ายวิชาการ ใจดี', 'pass': 'academic123', 'faculty': faculty, 'program': None},
    ]
    
    for u_data in users:
        if not User.query.filter_by(username=u_data['username']).first():
            user = User(
                username=u_data['username'], 
                role=u_data['role'], 
                full_name=u_data['full_name'],
                faculty_id=u_data['faculty'].id if u_data['faculty'] else None,
                program_id=u_data['program'].id if u_data['program'] else None
            )
            user.set_password(u_data['pass'])
            db.session.add(user)
            print(f"Created user: {u_data['username']} ({u_data['role']})")
    db.session.commit()

def seed_sample_data(program):
    """Create sample course and section data."""
    if not Course.query.filter_by(code='CS101').first():
        course = Course(
            code='CS101', 
            name_th='การเขียนโปรแกรมพื้นฐาน', 
            name_en='Introduction to Programming', 
            credits='3(2-2-5)',
            description='พื้นฐานการเขียนโปรแกรมคอมพิวเตอร์ ตรรกศาสตร์ ข้อมูล และโครงสร้างควบคุม',
            program_id=program.id
        )
        db.session.add(course)
        db.session.commit()
        print("Created sample course: CS101")

        term = Term.query.filter_by(year=2567, semester=1).first()
        if not term:
            term = Term(year=2567, semester=1)
            db.session.add(term)
            db.session.commit()
            print("Created term: 1/2567")

        instructor = User.query.filter_by(username='instructor1').first()
        if instructor:
            section = Section(
                course_id=course.id, 
                instructor_id=instructor.id, 
                term_id=term.id, 
                section_number='1',
                is_open=True,
                status='active'
            )
            db.session.add(section)
            db.session.commit()
            print("Created section 1 for CS101 (Open for editing)")

if __name__ == '__main__':
    with app.app_context():
        print("Starting database seeding...")
        db.create_all()
        f, p = seed_hierarchy()
        seed_users(f, p)
        seed_sample_data(p)
        print("Seeding complete!")

