from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class Faculty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    
    # Relationships
    programs = db.relationship('Program', backref='faculty', lazy=True)
    users = db.relationship('User', backref='faculty', lazy=True)

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    year = db.Column(db.Integer) # Add year to program (e.g. 2565)
    
    # Relationships
    users = db.relationship('User', backref='program', lazy=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # instructor, head, academic, admin
    full_name = db.Column(db.String(128), nullable=False)
    
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'))
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'))
    
    # Relationships
    sections = db.relationship('Section', backref='instructor', lazy=True)

    user_roles = db.relationship('UserRole', backref='user', lazy=True, cascade='all, delete-orphan')

    def role_names(self):
        roles = set()
        if self.role:
            roles.add(self.role)
        for r in self.user_roles or []:
            if r.role:
                roles.add(r.role)
        # stable order for UI
        order = {'admin': 0, 'academic': 1, 'head': 2, 'instructor': 3}
        return sorted(roles, key=lambda x: order.get(x, 99))

    def has_role(self, role_name: str) -> bool:
        return role_name in set(self.role_names())

    def has_any_role(self, role_names) -> bool:
        user_roles = set(self.role_names())
        return any(r in user_roles for r in role_names)

    def best_role(self) -> str:
        roles = self.role_names()
        return roles[0] if roles else (self.role or 'instructor')

    def set_roles(self, roles):
        roles = [r for r in (roles or []) if r]
        roles = list(dict.fromkeys(roles))
        self.user_roles = [UserRole(role=r) for r in roles]

        # Keep legacy column aligned for older code paths
        if roles:
            order = {'admin': 0, 'academic': 1, 'head': 2, 'instructor': 3}
            self.role = sorted(roles, key=lambda x: order.get(x, 99))[0]

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    name_th = db.Column(db.String(256), nullable=False)
    name_en = db.Column(db.String(256), nullable=False)
    credits = db.Column(db.String(10))
    description = db.Column(db.Text)
    
    program_id = db.Column(db.Integer, db.ForeignKey('program.id')) # Link course to program

    __table_args__ = (
        db.UniqueConstraint('program_id', 'code', name='uq_course_program_code'),
    )
    
    # Relationships
    program = db.relationship('Program', backref='courses')

class Term(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.Integer, nullable=False)  # 1, 2, 3


class TermProgram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('term_id', 'program_id', name='uq_term_program'),
    )

    term = db.relationship('Term', backref='term_programs')
    program = db.relationship('Program')

class Section(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # instructor assignment (Step C)
    term_id = db.Column(db.Integer, db.ForeignKey('term.id'), nullable=False)
    section_number = db.Column(db.String(10))
    
    is_open = db.Column(db.Boolean, default=False) # Step C: เริ่มกรอกได้
    status = db.Column(db.String(20), default='active') # active, locked, archived
    
    # Relationships
    course = db.relationship('Course', backref='sections')
    term = db.relationship('Term', backref='sections')
    tqf3 = db.relationship('TQF3', backref='section', uselist=False)
    tqf5 = db.relationship('TQF5', backref='section', uselist=False)

class TQF3(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), unique=True, nullable=False)
    status = db.Column(db.String(20), default='DRAFT')  # DRAFT, SUBMITTED, RETURNED, APPROVED
    submitted_at = db.Column(db.DateTime)
    
    # Detailed Data
    general_info = db.Column(db.JSON)
    clo_plo_mapping = db.Column(db.JSON)
    teaching_plan = db.Column(db.JSON)
    evaluation_plan = db.Column(db.JSON)

class TQF5(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), unique=True, nullable=False)
    tqf3_id = db.Column(db.Integer, db.ForeignKey('tqf3.id'), nullable=False)
    status = db.Column(db.String(20), default='DRAFT')  # DRAFT, SUBMITTED, RETURNED, APPROVED
    submitted_at = db.Column(db.DateTime)
    
    # Detailed Data
    actual_teaching = db.Column(db.JSON)
    grade_distribution = db.Column(db.JSON)
    improvements = db.Column(db.JSON)
    verification_result = db.Column(db.JSON)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tqf_type = db.Column(db.String(10))  # TQF3 or TQF5
    tqf_id = db.Column(db.Integer, nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    reviewer = db.relationship('User')


class CurriculumUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_filename = db.Column(db.String(255), nullable=True)
    curriculum_name_th = db.Column(db.String(256), nullable=True)
    faculty_name = db.Column(db.String(128), nullable=True)
    revision_year = db.Column(db.Integer, nullable=True)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    json_data = db.Column(db.JSON, nullable=False)

    program = db.relationship('Program')
    uploader = db.relationship('User')


class UserRole(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'role', name='uq_user_role'),
    )
