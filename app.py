import os, json
from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, UserRole, Course, Term, Section, TQF3, TQF5, Program, Faculty, Feedback, CurriculumUpload, TermProgram
import threading
from sqlalchemy import or_
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None

from functools import wraps

if load_dotenv:
    load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'tqf-secret-key-12345')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tqf_system.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

_schema_init_lock = threading.Lock()

ROLE_PRIORITY = ['admin', 'academic', 'head', 'instructor']


def _sync_legacy_user_roles():
    """Backfill UserRole rows from the legacy User.role column."""
    users = User.query.all()
    for u in users:
        if not u.role:
            continue
        exists = UserRole.query.filter_by(user_id=u.id, role=u.role).first()
        if not exists:
            db.session.add(UserRole(user_id=u.id, role=u.role))
    db.session.commit()


def users_with_role(role_name: str):
    return User.query.filter(
        or_(
            User.role == role_name,
            User.user_roles.any(UserRole.role == role_name),
        )
    )


def get_active_role():
    if not current_user.is_authenticated:
        return None
    available = current_user.role_names()
    chosen = session.get('active_role')
    if chosen in available:
        return chosen
    # If the user has multiple roles and must pick one, do not auto-select.
    if session.get('choose_role') and len(available) > 1:
        return None

    best = current_user.best_role()
    session['active_role'] = best
    session.pop('choose_role', None)
    return best


def _safe_redirect_next(default_endpoint: str, **default_kwargs):
    next_url = (request.form.get('next') or request.args.get('next') or '').strip()
    if next_url.startswith('/') and not next_url.startswith('//'):
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **default_kwargs))


def _ensure_schema_created():
    """Create missing tables without dropping existing data.

    This is needed because `flask run` does not execute the `__main__` block.
    Flask 3 also removed `before_first_request`, so we guard in `before_request`.
    """
    if app.config.get('_SCHEMA_READY'):
        return
    with _schema_init_lock:
        if app.config.get('_SCHEMA_READY'):
            return
        db.create_all()
        try:
            _sync_legacy_user_roles()
        except Exception:
            db.session.rollback()
        app.config['_SCHEMA_READY'] = True


@app.before_request
def _auto_create_schema_once():
    _ensure_schema_created()

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_any_role(roles):
                flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.context_processor
def _inject_roles_context():
    if not current_user.is_authenticated:
        return {}
    return {
        'active_role': get_active_role(),
        'available_roles': current_user.role_names(),
    }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_raw = request.form.get('username') or ''
        username = username_raw.strip()
        password = request.form.get('password')
        # Be forgiving about accidental whitespace in either input or existing DB values.
        user = (
            User.query
            .filter(
                or_(
                    User.username == username_raw,
                    User.username == username,
                    func.trim(User.username) == username,
                )
            )
            .first()
        )
        if user and user.check_password(password):
            login_user(user)
            roles = user.role_names()
            if len(roles) > 1:
                session.pop('active_role', None)
                session['choose_role'] = True
                return redirect(url_for('choose_role'))
            session['active_role'] = user.best_role()
            session.pop('choose_role', None)
            return redirect(url_for('dashboard'))
        flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('active_role', None)
    session.pop('choose_role', None)
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = get_active_role()
    if role is None:
        return redirect(url_for('choose_role'))
    if role == 'instructor':
        return redirect(url_for('instructor_dashboard'))
    elif role == 'head':
        return redirect(url_for('head_dashboard'))
    elif role == 'academic':
        return redirect(url_for('academic_dashboard'))
    elif role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return "Unknown Role"


@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """Account settings available to every role (e.g., change password)."""
    if request.method == 'POST':
        current_password = request.form.get('current_password') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not current_user.check_password(current_password):
            flash('รหัสผ่านปัจจุบันไม่ถูกต้อง', 'danger')
            return redirect(url_for('account'))

        if len(new_password) < 6:
            flash('รหัสผ่านใหม่ต้องมีอย่างน้อย 6 ตัวอักษร', 'danger')
            return redirect(url_for('account'))

        if new_password != confirm_password:
            flash('ยืนยันรหัสผ่านใหม่ไม่ตรงกัน', 'danger')
            return redirect(url_for('account'))

        user = User.query.get(current_user.id)
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('เปลี่ยนรหัสผ่านเรียบร้อย', 'success')
        return redirect(url_for('account'))

    return render_template('account.html')


@app.route('/choose-role', methods=['GET', 'POST'])
@login_required
def choose_role():
    roles = current_user.role_names()
    if len(roles) <= 1:
        session['active_role'] = current_user.best_role()
        session.pop('choose_role', None)
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        role = request.form.get('role')
        if role and current_user.has_role(role):
            session['active_role'] = role
            session.pop('choose_role', None)
            flash('เลือกบทบาทเรียบร้อย', 'success')
            return redirect(url_for('dashboard'))
        flash('กรุณาเลือกบทบาทที่ถูกต้อง', 'danger')

    return render_template('choose_role.html', roles=roles)


@app.route('/switch-role', methods=['POST'])
@login_required
def switch_role():
    role = request.form.get('role')
    if role and current_user.has_role(role):
        session['active_role'] = role
        session.pop('choose_role', None)
        flash(f'สลับบทบาทเป็น {role} แล้ว', 'success')
    else:
        flash('ไม่สามารถสลับบทบาทได้', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/instructor/dashboard')
@login_required
@roles_required('instructor')
def instructor_dashboard():
    # Show all assigned sections across all terms, with optional term filter
    selected_term_id = request.args.get('term_id', type=int)
    query = Section.query.filter(Section.instructor_id == current_user.id).join(Term)
    if selected_term_id:
        query = query.filter(Section.term_id == selected_term_id)
    sections = query.order_by(Term.year.desc(), Term.semester.desc(), Section.id.desc()).all()

    terms = (
        Term.query
        .join(Section, Section.term_id == Term.id)
        .filter(Section.instructor_id == current_user.id)
        .distinct()
        .order_by(Term.year.desc(), Term.semester.desc())
        .all()
    )
    return render_template('instructor/dashboard.html', sections=sections, terms=terms, selected_term_id=selected_term_id)

@app.route('/instructor/tqf3/<int:section_id>', methods=['GET', 'POST'])
@login_required
@roles_required('instructor')
def edit_tqf3(section_id):
    section = Section.query.get_or_404(section_id)
    if section.instructor_id != current_user.id:
        flash('คุณไม่มีสิทธิ์เข้าถึงรายวิชานี้', 'danger')
        return redirect(url_for('dashboard'))
    
    tqf3 = TQF3.query.filter_by(section_id=section_id).first()
    if not tqf3:
        tqf3 = TQF3(section_id=section_id, general_info={}, clo_plo_mapping={}, teaching_plan={}, evaluation_plan={})
        db.session.add(tqf3)
        db.session.commit()
    
    if request.method == 'POST':
        # Check if locked
        if tqf3.status in ['SUBMITTED', 'APPROVED']:
            flash('เอกสารถูกล็อกแล้ว ไม่สามารถแก้ไขได้', 'warning')
            return redirect(url_for('instructor_dashboard'))

        # Process multi-value fields (lists) correctly
        data = {}
        for key in request.form.keys():
            if key.endswith('[]'):
                data[key] = request.form.getlist(key)
            else:
                if key != 'action': # Don't save action in general_info
                    data[key] = request.form.get(key)
        
        tqf3.general_info = data
        
        # Handle Submission
        action = request.form.get('action')
        if action == 'submit':
            tqf3.status = 'SUBMITTED'
            tqf3.submitted_at = datetime.utcnow()
            flash('ส่ง มคอ.3 ให้หัวหน้าสาขาเรียบร้อยแล้ว', 'success')
        else:
            tqf3.status = 'DRAFT' if tqf3.status == 'RETURNED' else tqf3.status
            flash('บันทึกร่าง มคอ.3 สำเร็จ', 'success')
            
        db.session.commit()
        return redirect(url_for('instructor_dashboard'))
        
    # Fetch feedback history
    feedbacks = Feedback.query.filter_by(tqf_type='TQF3', tqf_id=tqf3.id).order_by(Feedback.created_at.desc()).all()
    
    return render_template('instructor/edit_tqf3.html', section=section, tqf3=tqf3, feedbacks=feedbacks)

@app.route('/instructor/tqf5/<int:section_id>', methods=['GET', 'POST'])
@login_required
@roles_required('instructor')
def edit_tqf5(section_id):
    section = Section.query.get_or_404(section_id)
    if section.instructor_id != current_user.id:
        flash('คุณไม่มีสิทธิ์เข้าถึงรายวิชานี้', 'danger')
        return redirect(url_for('dashboard'))
    
    tqf3 = TQF3.query.filter_by(section_id=section_id).first()
    if not tqf3:
        flash('กรุณาจัดทำ มคอ.3 ให้เรียบร้อยก่อนจัดทำ มคอ.5', 'warning')
        return redirect(url_for('instructor_dashboard'))
    
    tqf5 = TQF5.query.filter_by(section_id=section_id).first()
    if not tqf5:
        tqf5 = TQF5(section_id=section_id, tqf3_id=tqf3.id, actual_teaching={}, grade_distribution={}, improvements={}, verification_result={})
        db.session.add(tqf5)
        db.session.commit()
    
    if request.method == 'POST':
        # Check if locked
        if tqf5.status in ['SUBMITTED', 'APPROVED']:
            flash('เอกสารถูกล็อกแล้ว ไม่สามารถแก้ไขได้', 'warning')
            return redirect(url_for('instructor_dashboard'))

        # Process multi-value fields (lists) correctly
        data = {}
        for key in request.form.keys():
            if key.endswith('[]'):
                data[key] = request.form.getlist(key)
            else:
                if key != 'action':
                    data[key] = request.form.get(key)
        
        tqf5.actual_teaching = data
        
        # Handle Submission
        action = request.form.get('action')
        if action == 'submit':
            tqf5.status = 'SUBMITTED'
            tqf5.submitted_at = datetime.utcnow()
            flash('ส่ง มคอ.5 ให้หัวหน้าสาขาเรียบร้อยแล้ว', 'success')
        else:
            tqf5.status = 'DRAFT' if tqf5.status == 'RETURNED' else tqf5.status
            flash('บันทึกร่าง มคอ.5 สำเร็จ', 'success')
            
        db.session.commit()
        return redirect(url_for('instructor_dashboard'))
        
    # Fetch feedback history
    feedbacks = Feedback.query.filter_by(tqf_type='TQF5', tqf_id=tqf5.id).order_by(Feedback.created_at.desc()).all()
        
    return render_template('instructor/edit_tqf5.html', section=section, tqf5=tqf5, tqf3=tqf3, feedbacks=feedbacks)

@app.route('/head/dashboard')
@login_required
@roles_required('head')
def head_dashboard():
    # Filter Sections by Course's Program (the program current_user is head of)
    sections = Section.query.join(Course).filter(Course.program_id == current_user.program_id).all()
    # List of instructors in the same program for assignment dropdown
    instructors = users_with_role('instructor').filter(User.program_id == current_user.program_id).all()
    return render_template('head/dashboard.html', sections=sections, instructors=instructors)

@app.route('/head/review/<tqf_type>/<int:tqf_id>', methods=['GET', 'POST'])
@login_required
@roles_required('head')
def review_tqf(tqf_type, tqf_id):
    if tqf_type == 'tqf3':
        tqf = TQF3.query.get_or_404(tqf_id)
    else:
        tqf = TQF5.query.get_or_404(tqf_id)
        
    if request.method == 'POST':
        action = request.form.get('action') # approve or reject
        comment = request.form.get('comment')
        
        tqf.status = 'APPROVED' if action == 'approve' else 'RETURNED'
        if action == 'approve':
            tqf.submitted_at = datetime.utcnow()
            
        feedback = Feedback(tqf_type=tqf_type.upper(), tqf_id=tqf_id, reviewer_id=current_user.id, comment=comment)
        db.session.add(feedback)
        db.session.commit()
        
        flash(f'ดำเนินการเรียบร้อย: {tqf.status}', 'success')
        return redirect(url_for('head_dashboard'))
        
    return render_template('head/review.html', tqf=tqf, tqf_type=tqf_type)

# --- Admin Routes (Step A) ---

@app.route('/admin/faculties', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_faculties():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            faculty = Faculty(name=name)
            db.session.add(faculty)
            db.session.commit()
            flash('เพิ่มคณะเรียบร้อย', 'success')
    faculties = Faculty.query.all()
    return render_template('admin/faculties.html', faculties=faculties)

def _handle_programs_request():
    """Shared handler for program management pages (admin + academic)."""
    if request.method == 'POST':
        # Handle Curriculum JSON upload (store snapshot + import to DB)
        if 'curriculum_json' in request.files:
            from sqlalchemy.exc import IntegrityError
            file = request.files['curriculum_json']
            if not file or not file.filename:
                flash('กรุณาเลือกไฟล์ JSON', 'danger')
                return redirect(request.path)
            if not file.filename.lower().endswith('.json'):
                flash('ไฟล์ต้องเป็น .json เท่านั้น', 'danger')
                return redirect(request.path)

            try:
                json_data = json.load(file)
            except Exception as e:
                flash(f'เกิดข้อผิดพลาดในการอ่านไฟล์: {str(e)}', 'danger')
                return redirect(request.path)

            info = json_data.get('curriculum_info', {}) if isinstance(json_data, dict) else {}
            curriculum_name_th = info.get('name') if isinstance(info, dict) else None
            faculty_name = info.get('faculty') if isinstance(info, dict) else None
            revision_year_raw = (info.get('revision_year') or '') if isinstance(info, dict) else ''
            revision_digits = ''.join(ch for ch in revision_year_raw if ch.isdigit())
            revision_year = int(revision_digits) if revision_digits else None

            # Create/ensure Faculty + Program
            program_obj = None
            if faculty_name:
                faculty = Faculty.query.filter_by(name=faculty_name).first()
                if not faculty:
                    faculty = Faculty(name=faculty_name)
                    db.session.add(faculty)
                    db.session.commit()

                program_name = None
                if curriculum_name_th and 'สาขาวิชา' in curriculum_name_th:
                    program_name = curriculum_name_th.split('สาขาวิชา', 1)[1].strip() or None
                program_name = program_name or curriculum_name_th

                if program_name:
                    program_query = Program.query.filter_by(name=program_name, faculty_id=faculty.id)
                    if revision_year is not None:
                        program_query = program_query.filter_by(year=revision_year)
                    program_obj = program_query.first()
                    if not program_obj:
                        program_obj = Program(name=program_name, faculty_id=faculty.id, year=revision_year)
                        db.session.add(program_obj)
                        db.session.commit()

            # Determine which course codes belong to this curriculum
            def extract_course_codes(node):
                codes = []
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k == 'course_codes' and isinstance(v, list):
                            for code in v:
                                if isinstance(code, str) and code.strip():
                                    codes.append(code.strip())
                        else:
                            codes.extend(extract_course_codes(v))
                elif isinstance(node, list):
                    for item in node:
                        codes.extend(extract_course_codes(item))
                return codes

            curriculum_structure = json_data.get('curriculum_structure', {}) if isinstance(json_data, dict) else {}
            codes = extract_course_codes(curriculum_structure)
            # fallback: import all codes from courses catalog
            courses_catalog = json_data.get('courses', {}) if isinstance(json_data, dict) else {}
            if not codes and isinstance(courses_catalog, dict):
                codes = list(courses_catalog.keys())
            codes = sorted(set(codes))

            created = 0
            updated = 0
            missing = 0
            import_error = None
            needs_migration = False

            if program_obj and isinstance(courses_catalog, dict) and codes:
                try:
                    # Load existing courses once to avoid autoflush during per-item queries.
                    existing_courses = Course.query.filter_by(program_id=program_obj.id).all()
                    existing_by_code = {c.code: c for c in existing_courses}

                    for code in codes:
                        cinfo = courses_catalog.get(code)
                        if not isinstance(cinfo, dict):
                            missing += 1
                            continue
                        name_th = cinfo.get('name') or code
                        name_en = cinfo.get('name_en') or name_th
                        credits = cinfo.get('credits')
                        description = cinfo.get('description')

                        existing = existing_by_code.get(code)
                        if existing:
                            existing.name_th = name_th
                            existing.name_en = name_en
                            existing.credits = credits
                            existing.description = description
                            existing.program_id = program_obj.id
                            updated += 1
                        else:
                            db.session.add(Course(
                                code=code,
                                name_th=name_th,
                                name_en=name_en,
                                credits=credits,
                                description=description,
                                program_id=program_obj.id
                            ))
                            created += 1

                    db.session.commit()
                except IntegrityError as e:
                    db.session.rollback()
                    import_error = str(e)
                    if 'UNIQUE constraint failed: course.code' in import_error:
                        needs_migration = True
                except Exception as e:
                    db.session.rollback()
                    import_error = str(e)

            # Store snapshot in DB (copy file into DB)
            upload = CurriculumUpload(
                source_filename=file.filename,
                curriculum_name_th=curriculum_name_th,
                faculty_name=faculty_name,
                revision_year=revision_year,
                program_id=program_obj.id if program_obj else None,
                uploaded_by=current_user.id if current_user.is_authenticated else None,
                json_data=json_data,
            )
            db.session.add(upload)
            db.session.commit()

            if not program_obj:
                flash('บันทึกไฟล์หลักสูตรลงฐานข้อมูลแล้ว (ไม่สามารถสร้าง Program ได้จากไฟล์นี้)', 'warning')
            elif needs_migration:
                flash(
                    'บันทึกไฟล์หลักสูตรลงฐานข้อมูลแล้ว แต่คัดลอกรายวิชาเข้า DB ไม่สำเร็จ (โครงสร้าง DB ยังเป็นแบบเดิม) — '
                    'ให้รันคำสั่ง `flask --app app migrate-course-uniqueness` แล้วอัปโหลดใหม่อีกครั้ง',
                    'warning'
                )
            elif import_error:
                flash(
                    f'บันทึกไฟล์หลักสูตรลงฐานข้อมูลแล้ว แต่คัดลอกรายวิชาเข้า DB ไม่สำเร็จ: {import_error}',
                    'warning'
                )
            else:
                flash(f'บันทึกไฟล์หลักสูตรลงฐานข้อมูลแล้ว และคัดลอกรายวิชาเข้า DB: สร้าง {created}, อัปเดต {updated}, ไม่พบข้อมูล {missing}', 'success')
            return redirect(request.path)

        name = request.form.get('name')
        faculty_id = request.form.get('faculty_id')
        year = request.form.get('year')
        if name and faculty_id:
            program = Program(name=name, faculty_id=faculty_id, year=year or None)
            db.session.add(program)
            db.session.commit()
            flash('เพิ่มหลักสูตรเรียบร้อย', 'success')

    faculties = Faculty.query.all()
    programs = Program.query.all()
    uploads = CurriculumUpload.query.order_by(CurriculumUpload.uploaded_at.desc()).limit(10).all()
    return render_template('admin/programs.html', faculties=faculties, programs=programs, uploads=uploads)


@app.route('/admin/programs', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def admin_manage_programs():
    return _handle_programs_request()


@app.route('/academic/programs', methods=['GET', 'POST'])
@login_required
@roles_required('academic', 'admin')
def academic_manage_programs():
    return _handle_programs_request()


@app.cli.command('migrate-course-uniqueness')
def migrate_course_uniqueness():
    """Rebuild the Course table to allow duplicate codes across programs.

    This performs a SQLite table rebuild:
    - creates course_new with UNIQUE(program_id, code)
    - copies data from course
    - swaps tables

    Run this once after pulling the code change, without needing a full init-db.
    """
    from sqlalchemy import text

    with app.app_context():
        conn = db.engine.connect()
        tx = conn.begin()
        try:
            conn.execute(text('PRAGMA foreign_keys=OFF'))

            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS course_new (
                    id INTEGER PRIMARY KEY,
                    code VARCHAR(20) NOT NULL,
                    name_th VARCHAR(256) NOT NULL,
                    name_en VARCHAR(256) NOT NULL,
                    credits VARCHAR(10),
                    description TEXT,
                    program_id INTEGER,
                    FOREIGN KEY(program_id) REFERENCES program (id),
                    UNIQUE(program_id, code)
                )
            '''))

            conn.execute(text('''
                INSERT INTO course_new (id, code, name_th, name_en, credits, description, program_id)
                SELECT id, code, name_th, name_en, credits, description, program_id FROM course
            '''))

            conn.execute(text('DROP TABLE course'))
            conn.execute(text('ALTER TABLE course_new RENAME TO course'))
            conn.execute(text('PRAGMA foreign_keys=ON'))
            tx.commit()
            print('OK: migrated Course uniqueness to (program_id, code)')
        except Exception as e:
            tx.rollback()
            print(f'ERROR: migration failed: {e}')
            raise
        finally:
            conn.close()

@app.route('/admin/delete-program/<int:program_id>', methods=['POST'])
@login_required
@roles_required('admin')
def admin_delete_program(program_id):
    program = Program.query.get_or_404(program_id)
    courses = Course.query.filter_by(program_id=program_id).all()

    # Prevent deletion if any course is referenced by sections
    course_ids = [c.id for c in courses]
    if course_ids and Section.query.filter(Section.course_id.in_(course_ids)).first():
        flash('ไม่สามารถลบหลักสูตรนี้ได้ เนื่องจากมีรายวิชาที่ถูกเปิดสอน/มี Section อยู่', 'danger')
        return redirect(url_for('admin_manage_programs'))

    # Safe to delete: remove courses first, then program
    for c in courses:
        db.session.delete(c)
    db.session.delete(program)
    db.session.commit()
    if courses:
        flash(f'ลบหลักสูตรเรียบร้อยแล้ว (พร้อมลบรายวิชา {len(courses)} รายวิชา)', 'success')
    else:
        flash('ลบหลักสูตรเรียบร้อยแล้ว', 'success')
    return redirect(url_for('admin_manage_programs'))

@app.route('/admin/courses', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_courses():
    from models import Program, Course, Faculty
    if request.method == 'POST':
        # Handle Manual Add
        code = request.form.get('code')
        name_th = request.form.get('name_th')
        name_en = request.form.get('name_en')
        credits = request.form.get('credits')
        program_id = request.form.get('program_id')
        
        if code and name_th:
            course = Course(code=code, name_th=name_th, name_en=name_en, 
                            credits=credits, program_id=program_id or None)
            db.session.add(course)
            db.session.commit()
            flash('เพิ่มรายวิชาเรียบร้อย', 'success')
            
    programs = Program.query.all()
    selected_program_id = request.args.get('program_id')
    
    query = Course.query
    if selected_program_id:
        query = query.filter_by(program_id=selected_program_id)
    
    courses = query.all()
    
    # Group courses by program for display
    grouped_courses = {}
    for course in courses:
        prog_name = course.program.name if course.program else "Other"
        if course.program and course.program.year:
            prog_name += f" ({course.program.year})"
        
        if prog_name not in grouped_courses:
            grouped_courses[prog_name] = []
        grouped_courses[prog_name].append(course)

    return render_template('admin/courses.html', grouped_courses=grouped_courses, programs=programs, selected_program_id=selected_program_id)

@app.route('/admin/delete-course/<int:course_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    # Check if course has sections
    if Section.query.filter_by(course_id=course_id).first():
        flash('ไม่สามารถลบรายวิชานี้ได้ เนื่องจากมีการเปิดสอนในเทอมต่างๆ', 'danger')
    else:
        db.session.delete(course)
        db.session.commit()
        flash('ลบรายวิชาเรียบร้อยแล้ว', 'success')
    return redirect(url_for('manage_courses'))

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def manage_users():
    from werkzeug.security import generate_password_hash
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        roles = request.form.getlist('roles')
        faculty_id = request.form.get('faculty_id')
        program_id = request.form.get('program_id')

        if username and password:
            if not roles:
                flash('กรุณาเลือกบทบาทอย่างน้อย 1 บทบาท', 'danger')
                return redirect(url_for('manage_users'))

            # Normalize roles and choose a primary role for legacy column
            roles = [r for r in roles if r]
            roles = list(dict.fromkeys(roles))
            role_order = {r: i for i, r in enumerate(ROLE_PRIORITY)}
            primary_role = sorted(roles, key=lambda x: role_order.get(x, 99))[0]

            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                full_name=full_name,
                role=primary_role,
                faculty_id=faculty_id or None,
                program_id=program_id or None
            )
            db.session.add(user)
            try:
                db.session.flush()
                for r in roles:
                    db.session.add(UserRole(user_id=user.id, role=r))
                db.session.commit()
                flash('เพิ่มผู้ใช้เรียบร้อย', 'success')
            except IntegrityError:
                db.session.rollback()
                flash('ไม่สามารถเพิ่มผู้ใช้ได้ (ชื่อผู้ใช้อาจซ้ำกัน)', 'danger')
            
    users = User.query.all()
    faculties = Faculty.query.all()
    programs = Program.query.all()
    return render_template('admin/users.html', users=users, faculties=faculties, programs=programs)


@app.route('/admin/users/<int:user_id>/roles', methods=['POST'])
@login_required
@roles_required('admin')
def admin_update_user_roles(user_id):
    user = User.query.get_or_404(user_id)
    roles = request.form.getlist('roles')
    roles = [r for r in roles if r]
    roles = list(dict.fromkeys(roles))
    if not roles:
        flash('กรุณาเลือกบทบาทอย่างน้อย 1 บทบาท', 'danger')
        return redirect(url_for('manage_users'))

    role_order = {r: i for i, r in enumerate(ROLE_PRIORITY)}
    primary_role = sorted(roles, key=lambda x: role_order.get(x, 99))[0]

    # Replace role assignments
    UserRole.query.filter_by(user_id=user.id).delete()
    for r in roles:
        db.session.add(UserRole(user_id=user.id, role=r))
    user.role = primary_role
    db.session.commit()

    # Keep active role valid if the current user updated themselves
    if current_user.id == user.id:
        session.pop('active_role', None)
    flash('อัปเดตบทบาทเรียบร้อย', 'success')
    return redirect(url_for('manage_users'))

@app.route('/academic/dashboard')
@login_required
@roles_required('academic')
def academic_dashboard():
    selected_term_id = request.args.get('term_id', type=int)
    all_terms = Term.query.order_by(Term.year.desc(), Term.semester.desc()).all()
    if selected_term_id:
        selected_term = Term.query.get_or_404(selected_term_id)
        terms = [selected_term]
    else:
        terms = all_terms
    programs = Program.query.order_by(Program.year.desc().nullslast(), Program.name.asc()).all()
    programs_by_id = {p.id: p for p in programs}

    term_program_rows = TermProgram.query.all()
    term_program_ids = {}
    for tp in term_program_rows:
        term_program_ids.setdefault(tp.term_id, []).append(tp.program_id)
    
    # structure: { term_label: { 'term_id': id, 'programs': { program_id: { 'name': name, 'year': year } } } }
    grouped_data = {}
    
    for term in terms:
        term_label = f"{term.semester}/{term.year}"
        grouped_data[term_label] = {'term_id': term.id, 'programs': {}}

        # Add only programs explicitly attached to this term (TermProgram)
        for prog_id in sorted(term_program_ids.get(term.id, [])):
            prog = programs_by_id.get(prog_id)
            if prog:
                grouped_data[term_label]['programs'][prog.id] = {
                    'name': prog.name,
                    'year': prog.year,
                }
    
    # Calculate stats
    total = Section.query.count()
    
    # System Lock Status Detection
    # If there are active sections, the term is "open"
    # If all sections are locked (and there are sections), it's "locked"
    has_active = Section.query.filter_by(status='active').first() is not None
    has_locked = Section.query.filter_by(status='locked').first() is not None
    
    is_system_locked = not has_active and has_locked
    
    if total > 0:
        tqf3_submitted = Section.query.join(TQF3).filter(TQF3.status.in_(['SUBMITTED', 'APPROVED'])).count()
        tqf3_approved = Section.query.join(TQF3).filter(TQF3.status == 'APPROVED').count()
        tqf5_submitted = Section.query.join(TQF5).filter(TQF5.status.in_(['SUBMITTED', 'APPROVED'])).count()
        tqf5_approved = Section.query.join(TQF5).filter(TQF5.status == 'APPROVED').count()
        
        stats = {
            'total': total,
            'tqf3_perc': round((tqf3_submitted / total) * 100),
            'tqf3_app_perc': round((tqf3_approved / total) * 100),
            'tqf5_perc': round((tqf5_submitted / total) * 100),
            'tqf5_app_perc': round((tqf5_approved / total) * 100),
        }
    else:
        stats = {'total': 0, 'tqf3_perc': 0, 'tqf3_app_perc': 0, 'tqf5_perc': 0, 'tqf5_app_perc': 0}

    return render_template('academic/dashboard.html', 
                           grouped_data=grouped_data, 
                           stats=stats, 
                           is_system_locked=is_system_locked,
                           programs=programs,
                           term_program_ids=term_program_ids,
                           terms=all_terms,
                           selected_term_id=selected_term_id)


@app.route('/academic/term/<int:term_id>/program/<int:program_id>')
@login_required
@roles_required('academic')
def academic_term_program(term_id, program_id):
    term = Term.query.get_or_404(term_id)
    program = Program.query.get_or_404(program_id)

    tp = TermProgram.query.filter_by(term_id=term.id, program_id=program.id).first()
    if not tp:
        flash('หลักสูตรนี้ยังไม่ได้ถูกเพิ่มในเทอมนี้', 'warning')
        return redirect(url_for('academic_dashboard'))

    has_active = Section.query.filter_by(status='active').first() is not None
    has_locked = Section.query.filter_by(status='locked').first() is not None
    is_system_locked = not has_active and has_locked

    sections = (
        Section.query
        .join(Course, Section.course_id == Course.id)
        .filter(Section.term_id == term.id, Course.program_id == program.id)
        .order_by(Course.code.asc(), Section.section_number.asc())
        .all()
    )

    courses = Course.query.filter_by(program_id=program.id).order_by(Course.code.asc()).all()
    instructors = users_with_role('instructor').order_by(User.full_name.asc()).all()

    courses_grouped = {}
    for s in sections:
        label = f"{s.course.code} - {s.course.name_th}"
        courses_grouped.setdefault(label, []).append(s)

    return render_template(
        'academic/term_program.html',
        term=term,
        program=program,
        courses=courses,
        courses_grouped=courses_grouped,
        instructors=instructors,
        is_system_locked=is_system_locked,
    )


@app.route('/academic/add-program-to-term', methods=['POST'])
@login_required
@roles_required('academic')
def academic_add_program_to_term():
    term_id = request.form.get('term_id', type=int)
    program_id = request.form.get('program_id', type=int)
    if not term_id or not program_id:
        flash('ข้อมูลไม่ครบถ้วน', 'danger')
        return redirect(url_for('academic_dashboard'))

    has_active = Section.query.filter_by(status='active').first() is not None
    has_locked = Section.query.filter_by(status='locked').first() is not None
    is_system_locked = not has_active and has_locked
    if is_system_locked:
        flash('ระบบถูกล็อกอยู่ ไม่สามารถเพิ่มหลักสูตรในเทอมได้', 'warning')
        return redirect(url_for('academic_dashboard'))

    term = Term.query.get_or_404(term_id)
    program = Program.query.get_or_404(program_id)

    exists = TermProgram.query.filter_by(term_id=term.id, program_id=program.id).first()
    if exists:
        flash('หลักสูตรนี้ถูกเพิ่มในเทอมนี้แล้ว', 'info')
        return redirect(url_for('academic_dashboard'))

    db.session.add(TermProgram(term_id=term.id, program_id=program.id))
    db.session.commit()
    flash(f'เพิ่มหลักสูตร {program.name} ({program.year}) ในปีการศึกษา {term.semester}/{term.year} แล้ว', 'success')
    return redirect(url_for('academic_dashboard'))


@app.route('/academic/bulk-open-courses', methods=['POST'])
@login_required
@roles_required('academic')
def academic_bulk_open_courses():
    term_id = request.form.get('term_id', type=int)
    program_id = request.form.get('program_id', type=int)
    section_number = (request.form.get('section_number') or '1').strip()
    course_ids = request.form.getlist('course_ids')

    has_active = Section.query.filter_by(status='active').first() is not None
    has_locked = Section.query.filter_by(status='locked').first() is not None
    is_system_locked = not has_active and has_locked
    if is_system_locked:
        flash('ระบบถูกล็อกอยู่ ไม่สามารถเปิดรายวิชาเพิ่มได้', 'warning')
        return redirect(url_for('academic_dashboard'))

    if not term_id or not program_id or not course_ids:
        flash('กรุณาเลือกอย่างน้อย 1 รายวิชา', 'danger')
        return redirect(url_for('academic_dashboard'))

    term = Term.query.get_or_404(term_id)
    program = Program.query.get_or_404(program_id)

    # Ensure the program is attached to this term
    if not TermProgram.query.filter_by(term_id=term.id, program_id=program.id).first():
        db.session.add(TermProgram(term_id=term.id, program_id=program.id))

    created = 0
    skipped = 0
    for cid in course_ids:
        try:
            cid_int = int(cid)
        except ValueError:
            skipped += 1
            continue

        course = Course.query.get(cid_int)
        if not course or course.program_id != program.id:
            skipped += 1
            continue

        exists = Section.query.filter_by(term_id=term.id, course_id=course.id, section_number=section_number).first()
        if exists:
            skipped += 1
            continue

        db.session.add(Section(
            course_id=course.id,
            term_id=term.id,
            section_number=section_number,
            instructor_id=None,
            is_open=True
        ))
        created += 1

    db.session.commit()
    flash(f'เพิ่มรายวิชาเปิดสอนแล้ว: สร้าง {created} รายการ, ข้าม {skipped} รายการ (ซ้ำ/ไม่ถูกต้อง)', 'success')
    return _safe_redirect_next('academic_dashboard')


@app.route('/academic/remove-program-from-term', methods=['POST'])
@login_required
@roles_required('academic')
def academic_remove_program_from_term():
    term_id = request.form.get('term_id', type=int)
    program_id = request.form.get('program_id', type=int)
    if not term_id or not program_id:
        flash('ข้อมูลไม่ครบถ้วน', 'danger')
        return redirect(url_for('academic_dashboard'))

    has_active = Section.query.filter_by(status='active').first() is not None
    has_locked = Section.query.filter_by(status='locked').first() is not None
    is_system_locked = not has_active and has_locked
    if is_system_locked:
        flash('ระบบถูกล็อกอยู่ ไม่สามารถลบหลักสูตรออกจากเทอมได้', 'warning')
        return redirect(url_for('academic_dashboard'))

    term = Term.query.get_or_404(term_id)
    program = Program.query.get_or_404(program_id)

    # Block removal if there are already opened sections for this term + program
    existing_section = (
        Section.query
        .join(Course, Section.course_id == Course.id)
        .filter(Section.term_id == term.id, Course.program_id == program.id)
        .first()
    )
    if existing_section:
        flash('ลบหลักสูตรออกจากเทอมนี้ไม่ได้ เพราะมีรายวิชาที่เปิดสอนแล้ว (ให้ลบรายวิชาเปิดสอนก่อน)', 'danger')
        return redirect(url_for('academic_dashboard'))

    tp = TermProgram.query.filter_by(term_id=term.id, program_id=program.id).first()
    if not tp:
        flash('ไม่พบหลักสูตรนี้ในเทอมดังกล่าว', 'info')
        return redirect(url_for('academic_dashboard'))

    db.session.delete(tp)
    db.session.commit()
    flash(f'ลบหลักสูตร {program.name} ({program.year}) ออกจากปีการศึกษา {term.semester}/{term.year} แล้ว', 'success')
    return _safe_redirect_next('academic_dashboard')

@app.route('/academic/manage-terms', methods=['GET', 'POST'])
@login_required
@roles_required('academic', 'admin')
def manage_terms():
    if request.method == 'POST':
        year = request.form.get('year')
        semester = request.form.get('semester')
        if year and semester:
            term = Term(year=int(year), semester=int(semester))
            db.session.add(term)
            db.session.commit()
            flash('เพิ่มปีการศึกษา/ภาคเรียนเรียบร้อย', 'success')
    
    terms = Term.query.order_by(Term.year.desc(), Term.semester.desc()).all()
    return render_template('academic/manage_terms.html', terms=terms)

@app.route('/academic/delete-term/<int:term_id>', methods=['POST'])
@login_required
@roles_required('academic', 'admin')
def delete_term(term_id):
    term = Term.query.get_or_404(term_id)
    # Check if term has sections
    if Section.query.filter_by(term_id=term_id).first():
        flash('ไม่สามารถลบปีการศึกษานี้ได้ เนื่องจากมีการเปิดรายวิชาสอนแล้ว', 'danger')
    else:
        db.session.delete(term)
        db.session.commit()
        flash('ลบปีการศึกษาเรียบร้อยแล้ว', 'success')
    return redirect(url_for('manage_terms'))

@app.route('/academic/lock-term', methods=['POST'])
@login_required
@roles_required('academic')
def lock_term():
    # Step F - Archive current term
    sections = Section.query.filter_by(status='active').all()
    for s in sections:
        s.status = 'locked'
        s.is_open = False
    db.session.commit()
    flash('ทำการปิดรอบและล็อกเอกสารเรียบร้อยแล้ว', 'warning')
    return _safe_redirect_next('academic_dashboard')

@app.route('/academic/unlock-term', methods=['POST'])
@login_required
@roles_required('academic')
def unlock_term():
    # Open the system for instructors: ensure all non-archived sections are active + open
    sections = Section.query.filter(Section.status.in_(['active', 'locked'])).all()
    for s in sections:
        s.status = 'active'
        s.is_open = True
    db.session.commit()
    flash('ทำการเปิดรอบและปลดล็อกเอกสารเรียบร้อยแล้ว', 'success')
    return _safe_redirect_next('academic_dashboard')

@app.route('/academic/open-course', methods=['GET', 'POST'])
@login_required
@roles_required('academic')
def open_course():
    if request.method == 'POST':
        has_active = Section.query.filter_by(status='active').first() is not None
        has_locked = Section.query.filter_by(status='locked').first() is not None
        is_system_locked = not has_active and has_locked
        if is_system_locked:
            flash('ระบบถูกล็อกอยู่ ไม่สามารถเปิดรายวิชาเพิ่มได้', 'warning')
            return redirect(url_for('academic_dashboard'))

        course_id = request.form.get('course_id')
        term_id = request.form.get('term_id')
        instructor_id = request.form.get('instructor_id')
        section_number = request.form.get('section_number', '1')
        
        if course_id and term_id:
            course = Course.query.get(course_id)
            if course and course.program_id:
                if not TermProgram.query.filter_by(term_id=term_id, program_id=course.program_id).first():
                    db.session.add(TermProgram(term_id=term_id, program_id=course.program_id))

            existing = Section.query.filter_by(
                course_id=course_id,
                term_id=term_id,
                section_number=section_number
            ).first()
            if existing:
                flash('มีการเปิดรายวิชานี้ (หมู่เรียนนี้) แล้วในเทอมดังกล่าว', 'warning')
                return redirect(url_for('academic_dashboard'))

            section = Section(
                course_id=course_id, 
                term_id=term_id, 
                section_number=section_number,
                instructor_id=instructor_id or None,
                is_open=True
            )
            db.session.add(section)
            db.session.commit()
            flash('เปิดรายวิชาสอนและมอบหมายผู้สอนเรียบร้อย', 'success')
            return _safe_redirect_next('academic_dashboard')
            
    courses = Course.query.all()
    terms = Term.query.order_by(Term.year.desc(), Term.semester.desc()).all()
    instructors = users_with_role('instructor').all()
    
    # Pre-fill from query params
    selected_term_id = request.args.get('term_id', type=int)
    selected_program_id = request.args.get('program_id', type=int)
    
    # Group courses by program for the UI
    grouped_courses = {}
    for c in courses:
        prog_name = c.program.name if c.program else "รายวิชาทั่วไป"
        prog_id = c.program_id if c.program_id else 0
        if prog_id not in grouped_courses:
            grouped_courses[prog_id] = {'name': prog_name, 'courses': []}
        grouped_courses[prog_id]['courses'].append(c)

    return render_template('academic/open_course.html', 
                          grouped_courses=grouped_courses, 
                          terms=terms, 
                          instructors=instructors,
                          selected_term_id=selected_term_id,
                          selected_program_id=selected_program_id)

@app.route('/academic/assign-instructor/<int:section_id>', methods=['POST'])
@login_required
@roles_required('academic', 'head')
def assign_instructor(section_id):
    section = Section.query.get_or_404(section_id)
    instructor_id = request.form.get('instructor_id')
    if instructor_id:
        section.instructor_id = instructor_id
        db.session.commit()
        flash('มอบหมายผู้สอนเรียบร้อย', 'success')

    if (get_active_role() or current_user.role) == 'academic':
        return _safe_redirect_next('academic_dashboard')
    return _safe_redirect_next('head_dashboard')

@app.route('/head/toggle-open/<int:section_id>', methods=['POST'])
@login_required
@roles_required('head')
def toggle_open(section_id):
    section = Section.query.get_or_404(section_id)
    section.is_open = not section.is_open
    db.session.commit()
    flash(f'สถานะเอกสาร: {"เปิดให้เริ่มกรอก" if section.is_open else "ปิดห้ามกรอก"}', 'info')
    return redirect(url_for('head_dashboard'))

@app.route('/academic/delete-section/<int:section_id>', methods=['POST'])
@login_required
@roles_required('academic')
def delete_section(section_id):
    section = Section.query.get_or_404(section_id)
    # Check if has TQF documents
    if section.tqf3 or section.tqf5:
         flash('ไม่สามารถลบได้ เนื่องจากมีการสร้างเอกสาร มคอ. แล้ว', 'danger')
    else:
        db.session.delete(section)
        db.session.commit()
        flash('ลบรายวิชาที่เปิดสอนเรียบร้อยแล้ว', 'success')
    return _safe_redirect_next('academic_dashboard')

@app.route('/admin/dashboard')
@login_required
@roles_required('admin')
def admin_dashboard():
    return render_template('admin/dashboard.html')

# --- Database Initialization ---

@app.cli.command("init-db")
def init_db():
    from seed_data import seed_hierarchy, seed_users, seed_sample_data
    db.drop_all()
    db.create_all()
    f, p = seed_hierarchy()
    seed_users(f, p)
    seed_sample_data(p)
    print("Database reset, initialized and seeded with new hierarchy.")


@app.cli.command("create-tables")
def create_tables():
    """Create any missing tables without dropping data."""
    _ensure_schema_created()
    print("Ensured database tables exist (create_all).")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, port=port)
