from app import app, db
from models import Course, Program

with app.app_context():
    p = Program.query.filter_by(name='เทคโนโลยีมัลติมีเดีย').first()
    if p:
        courses = Course.query.filter_by(program_id=p.id).all()
        print(f"Program: {p.name} ({p.year})")
        print(f"Total courses found: {len(courses)}")
        for c in courses[:10]:
            print(f"- {c.code}: {c.name_th}")
    else:
        print("Program not found")
