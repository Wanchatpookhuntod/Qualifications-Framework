from app import app, db
from models import User, Course, Term, Section, Faculty, Program, TQF3, TQF5
from werkzeug.security import generate_password_hash

def clean_and_seed():
    with app.app_context():
        print("Cleaning database...")
        # Clear all data in correct order
        try:
            TQF5.query.delete()
            TQF3.query.delete()
            Section.query.delete()
            Course.query.delete()
            Program.query.delete()
            User.query.delete()
            Faculty.query.delete()
            Term.query.delete()
            db.session.commit()
            print("Database cleared successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"Error cleaning database: {e}")
            return

        # Seed initial users to allow re-login
        print("Seeding initial users...")
        admin = User(
            username='admin',
            password_hash=generate_password_hash('password'),
            role='admin',
            full_name='System Administrator'
        )
        academic = User(
            username='academic',
            password_hash=generate_password_hash('password'),
            role='academic',
            full_name='Academic Officer'
        )
        db.session.add(admin)
        db.session.add(academic)
        db.session.commit()
        print("Initial users created: admin/password, academic/password")

if __name__ == '__main__':
    clean_and_seed()
