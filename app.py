import json
import os
import csv
import io
import re
from datetime import datetime
from functools import wraps

try:
    from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
except ModuleNotFoundError as e:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: Flask.\n\n"
        "You are likely running app.py with the wrong Python interpreter (e.g. pyenv/system) "
        "instead of the project virtualenv.\n\n"
        "Fix:\n"
        "  1) source .venv/bin/activate\n"
        "  2) python -m pip install -r requirements.txt\n"
        "  3) python app.py\n\n"
        "Or run explicitly:\n"
        "  .venv/bin/python app.py\n"
    ) from e
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from models import (
    Course,
    Department,
    Faculty,
    Feedback,
    Program,
    Section,
    Term,
    TermProgram,
    TQF3,
    TQF5,
    User,
)

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    load_dotenv = None


if load_dotenv:
    load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "tqf-secret-key-12345")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ROLE_PRIORITY = ["admin", "academic", "head", "instructor"]


def _normalize_header_key(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", "", value)
    return value


_COURSE_HEADER_MAP = {
    # code
    "code": "code",
    "coursecode": "code",
    "รหัสวิชา": "code",
    "รหัส": "code",
    # name (thai)
    "name": "name_th",
    "nameth": "name_th",
    "name_th": "name_th",
    "coursetitle": "name_th",
    "ชื่อวิชา": "name_th",
    "ชื่อรายวิชา": "name_th",
    "ชื่อวิชาไทย": "name_th",
    "ชื่อ": "name_th",
    # name (en)
    "nameen": "name_en",
    "name_en": "name_en",
    "englishname": "name_en",
    "ชื่ออังกฤษ": "name_en",
    "ชื่อวิชาภาษาอังกฤษ": "name_en",
    # credits
    "credits": "credits",
    "credit": "credits",
    "หน่วยกิต": "credits",
    "หน่วยกิจ": "credits",
    # description
    "description": "description",
    "desc": "description",
    "คำอธิบาย": "description",
    "คำอธิบายรายวิชา": "description",
}


def _detect_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except Exception:
        return ","


def _override_delimiter_from_first_line(text: str, current: str) -> str:
    """Heuristic override for delimiter when sniffer falls back incorrectly."""
    if not text:
        return current
    first_line = ""
    for ln in text.splitlines():
        if ln.strip():
            first_line = ln
            break
    if not first_line:
        return current

    # Markdown table style often looks like: | a | b | c |
    if "|" in first_line and first_line.count("|") >= 2:
        return "|"
    if "\t" in first_line:
        return "\t"
    if ";" in first_line and "," not in first_line:
        return ";"
    return current


def _parse_courses_upload_text(text: str, filename: str) -> dict:
    """Parse upload file into normalized course dicts.

    Returns:
      {"ok": bool, "courses": List[Dict], "errors": List[str], "detected": Dict}
    """
    text = text or ""
    filename = filename or ""
    ext = os.path.splitext(filename)[1].lower()

    stripped = text.strip("\ufeff\n\r\t ")
    if not stripped:
        return {"ok": False, "courses": [], "errors": ["ไฟล์ว่าง"], "detected": {"type": "empty"}}

    # JSON
    if ext == ".json" or stripped.lstrip().startswith("{") or stripped.lstrip().startswith("["):
        try:
            obj = json.loads(stripped)
        except Exception as e:
            return {"ok": False, "courses": [], "errors": [f"JSON ไม่ถูกต้อง: {e}"], "detected": {"type": "json"}}

        detected = {"type": "json"}
        if isinstance(obj, dict) and isinstance(obj.get("courses"), dict):
            detected["shape"] = "dict.courses"
            raw_courses = list(obj.get("courses").values())
        elif isinstance(obj, list):
            detected["shape"] = "list"
            raw_courses = obj
        elif isinstance(obj, dict):
            detected["shape"] = "dict"
            values = list(obj.values())
            if values and sum(1 for v in values if isinstance(v, dict)) >= max(1, int(len(values) * 0.6)):
                raw_courses = [v for v in values if isinstance(v, dict)]
            else:
                raw_courses = [obj]
        else:
            raw_courses = []

        courses = []
        errors = []
        for idx, c in enumerate(raw_courses, start=1):
            if not isinstance(c, dict):
                errors.append(f"รายการที่ {idx}: ต้องเป็น object")
                continue
            code = (c.get("code") or c.get("รหัสวิชา") or "").strip()
            name_th = (
                c.get("name")
                or c.get("name_th")
                or c.get("ชื่อวิชา")
                or c.get("ชื่อรายวิชา")
                or c.get("ชื่อวิชาไทย")
                or ""
            ).strip()
            name_en = (c.get("name_en") or c.get("ชื่ออังกฤษ") or "").strip()
            description = (c.get("description") or c.get("คำอธิบาย") or c.get("คำอธิบายรายวิชา") or "").strip()
            credits = (c.get("credits") or c.get("หน่วยกิต") or c.get("หน่วยกิจ") or "")
            credits = str(credits).strip() if credits is not None else ""

            if not code or not name_th:
                errors.append(f"รายการที่ {idx}: ต้องมี code และ name (ชื่อวิชาไทย)")
                continue

            courses.append(
                {
                    "code": code,
                    "name_th": name_th,
                    "name_en": name_en,
                    "description": description,
                    "credits": credits or None,
                }
            )

        return {
            "ok": len(courses) > 0 and len(errors) == 0,
            "courses": courses,
            "errors": errors,
            "detected": detected,
        }

    # CSV/TXT delimited
    sample = stripped[:2048]
    delimiter = _override_delimiter_from_first_line(stripped, _detect_delimiter(sample))

    def split_parts(line: str) -> list:
        parts = [c.strip() for c in (line or "").split(delimiter)]
        while parts and parts[0] == "":
            parts.pop(0)
        while parts and parts[-1] == "":
            parts.pop()
        return parts

    def normalize_row(row: dict) -> dict:
        normalized = {}
        for k, v in (row or {}).items():
            if k is None:
                continue
            key = _normalize_header_key(str(k))
            mapped = _COURSE_HEADER_MAP.get(key)
            if not mapped:
                continue
            normalized[mapped] = (str(v).strip() if v is not None else "")
        return normalized

    errors = []
    courses = []

    if ext == ".csv":
        f = io.StringIO(stripped)
        reader = csv.DictReader(f, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        detected = {"type": "csv", "delimiter": delimiter, "headers": fieldnames}

        for idx, row in enumerate(reader, start=2):
            n = normalize_row(row)
            code = (n.get("code") or "").strip()
            name_th = (n.get("name_th") or "").strip()
            if not code or not name_th:
                errors.append(f"บรรทัด {idx}: ต้องมีรหัสวิชา (code) และชื่อวิชา (name_th)")
                continue
            courses.append(
                {
                    "code": code,
                    "name_th": name_th,
                    "name_en": (n.get("name_en") or "").strip(),
                    "description": (n.get("description") or "").strip(),
                    "credits": (n.get("credits") or "").strip() or None,
                }
            )

        if not courses and not errors:
            errors.append("ไม่พบข้อมูลรายวิชาในไฟล์")

        return {"ok": len(courses) > 0 and len(errors) == 0, "courses": courses, "errors": errors, "detected": detected}

    # TXT: header or no-header
    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    detected = {"type": "txt", "delimiter": delimiter, "lines": len(lines)}
    if not lines:
        return {"ok": False, "courses": [], "errors": ["ไฟล์ว่าง"], "detected": detected}

    header_parts = split_parts(lines[0])
    header_norm = [_normalize_header_key(c) for c in header_parts]
    looks_like_header = any(k in _COURSE_HEADER_MAP for k in header_norm)
    detected["header_like"] = looks_like_header

    start_idx = 1 if looks_like_header else 0
    for i, ln in enumerate(lines[start_idx:], start=(2 if looks_like_header else 1)):
        parts = split_parts(ln)
        if looks_like_header:
            row = {header_parts[j]: (parts[j] if j < len(parts) else "") for j in range(len(header_parts))}
            n = normalize_row(row)
            code = (n.get("code") or "").strip()
            name_th = (n.get("name_th") or "").strip()
            if not code or not name_th:
                errors.append(f"บรรทัด {i}: ต้องมีรหัสวิชา (code) และชื่อวิชา (name_th)")
                continue
            courses.append(
                {
                    "code": code,
                    "name_th": name_th,
                    "name_en": (n.get("name_en") or "").strip(),
                    "description": (n.get("description") or "").strip(),
                    "credits": (n.get("credits") or "").strip() or None,
                }
            )
        else:
            # Position-based: code | name_th | name_en | description | credits
            code = parts[0] if len(parts) > 0 else ""
            name_th = parts[1] if len(parts) > 1 else ""
            name_en = parts[2] if len(parts) > 2 else ""
            description = parts[3] if len(parts) > 3 else ""
            credits = parts[4] if len(parts) > 4 else ""

            if not code or not name_th:
                errors.append(
                    f"บรรทัด {i}: รูปแบบต้องเป็น code{delimiter}name_th{delimiter}name_en(optional){delimiter}description(optional){delimiter}credits(optional)"
                )
                continue

            courses.append(
                {
                    "code": code.strip(),
                    "name_th": name_th.strip(),
                    "name_en": name_en.strip(),
                    "description": description.strip(),
                    "credits": credits.strip() or None,
                }
            )

    if not courses and not errors:
        errors.append("ไม่พบข้อมูลรายวิชาในไฟล์")

    return {"ok": len(courses) > 0 and len(errors) == 0, "courses": courses, "errors": errors, "detected": detected}


def _import_courses_into_program(program: Program, parsed_courses: list) -> dict:
    """Upsert Course documents by (program_id + code)."""
    existing = program.courses if program and program.id else []
    by_code = {}
    for c in existing:
        key = (c.code or "").strip()
        if key and key not in by_code:
            by_code[key] = c

    created = 0
    updated = 0
    skipped = 0
    for row in parsed_courses or []:
        code = (row.get("code") or "").strip()
        name_th = (row.get("name_th") or "").strip()
        if not code or not name_th:
            skipped += 1
            continue

        existing_course = by_code.get(code)
        if existing_course:
            # Update fields (merge-friendly)
            existing_course.name_th = name_th
            existing_course.name_en = (row.get("name_en") or existing_course.name_en or "").strip()
            existing_course.description = (row.get("description") or existing_course.description or "")
            existing_course.credits = row.get("credits") or existing_course.credits
            existing_course.program_id = program.id
            existing_course.save()
            updated += 1
        else:
            Course(
                code=code,
                name_th=name_th,
                name_en=(row.get("name_en") or "").strip(),
                description=(row.get("description") or "") or None,
                credits=row.get("credits"),
                program_id=program.id,
            ).save()
            created += 1

    return {"created": created, "updated": updated, "skipped": skipped, "total": len(parsed_courses or [])}


def _validate_courses_upload_text(text: str, filename: str) -> dict:
    """Validate curriculum upload file containing course rows.

    Expected formats:
    - CSV with header row containing at least: code + name_th (header names can be Thai/English)
    - Delimited text (.txt) with header row, or without header as: code, name_th, credits(optional), name_en(optional)
    """
    text = text or ""
    filename = filename or ""
    ext = os.path.splitext(filename)[1].lower()

    # Remove empty lines at start/end to help Sniffer.
    stripped = text.strip("\ufeff\n\r\t ")
    if not stripped:
        return {
            "ok": False,
            "rows": 0,
            "errors": ["ไฟล์ว่าง"],
            "detected": {"type": "empty"},
        }

    sample = stripped[:2048]
    delimiter = _detect_delimiter(sample)
    delimiter = _override_delimiter_from_first_line(stripped, delimiter)

    # JSON curriculum/course dump support (e.g. multimedia_curriculum.json)
    if ext == ".json" or stripped.lstrip().startswith("{") or stripped.lstrip().startswith("["):
        try:
            obj = json.loads(stripped)
        except Exception as e:
            return {
                "ok": False,
                "rows": 0,
                "rows_ok": 0,
                "errors": [f"JSON ไม่ถูกต้อง: {e}"],
                "detected": {"type": "json"},
            }

        # Accept structures:
        # 1) {"courses": {"CODE": {course...}, ...}}
        # 2) [{course...}, {course...}]
        # 3) {"CODE": {course...}, ...}
        courses = None
        detected = {"type": "json"}
        if isinstance(obj, dict) and isinstance(obj.get("courses"), dict):
            detected["shape"] = "dict.courses"
            courses = list(obj.get("courses").values())
        elif isinstance(obj, list):
            detected["shape"] = "list"
            courses = obj
        elif isinstance(obj, dict):
            detected["shape"] = "dict"
            # Heuristic: treat values as courses if most values are dicts.
            values = list(obj.values())
            if values and sum(1 for v in values if isinstance(v, dict)) >= max(1, int(len(values) * 0.6)):
                courses = [v for v in values if isinstance(v, dict)]
            else:
                courses = [obj]
        else:
            courses = []

        errors = []
        rows_total = 0
        rows_ok = 0
        for idx, course in enumerate(courses, start=1):
            rows_total += 1
            if not isinstance(course, dict):
                errors.append(f"รายการที่ {idx}: ต้องเป็น object")
                continue
            code = (course.get("code") or course.get("รหัสวิชา") or "").strip()
            name_th = (course.get("name") or course.get("name_th") or course.get("ชื่อวิชา") or course.get("ชื่อรายวิชา") or course.get("ชื่อวิชาไทย") or "").strip()
            if not code or not name_th:
                errors.append(f"รายการที่ {idx}: ต้องมี code และ name (ชื่อวิชาไทย)")
                continue
            rows_ok += 1

        ok = rows_total > 0 and rows_ok == rows_total
        if rows_total == 0:
            errors.append("ไม่พบข้อมูลรายวิชาในไฟล์ JSON")

        return {
            "ok": ok,
            "rows": rows_total,
            "rows_ok": rows_ok,
            "errors": errors,
            "detected": detected,
        }

    # Only treat actual .csv as CSV. For .txt (including pipe-delimited table rows),
    # use the TXT/delimited parser which supports both header and no-header.
    treat_as_csv = ext == ".csv"

    errors = []
    rows_ok = 0
    rows_total = 0
    detected = {"type": "csv" if treat_as_csv else "delimited", "delimiter": delimiter}

    def normalize_row(row: dict) -> dict:
        normalized = {}
        for k, v in (row or {}).items():
            if k is None:
                continue
            key = _normalize_header_key(str(k))
            mapped = _COURSE_HEADER_MAP.get(key)
            if not mapped:
                continue
            normalized[mapped] = (str(v).strip() if v is not None else "")
        return normalized

    if treat_as_csv:
        # Try DictReader (header row).
        f = io.StringIO(stripped)
        reader = csv.DictReader(f, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        detected["headers"] = fieldnames

        mapped_headers = []
        for h in fieldnames:
            mapped_headers.append(_COURSE_HEADER_MAP.get(_normalize_header_key(h), ""))
        detected["mapped_headers"] = mapped_headers

        for idx, row in enumerate(reader, start=2):
            rows_total += 1
            n = normalize_row(row)
            code = (n.get("code") or "").strip()
            name_th = (n.get("name_th") or "").strip()
            if not code or not name_th:
                errors.append(f"บรรทัด {idx}: ต้องมีรหัสวิชา (code) และชื่อวิชา (name_th)")
            else:
                rows_ok += 1

        if rows_total == 0:
            errors.append("ไม่พบข้อมูลรายวิชาในไฟล์")

    else:
        # Delimited TXT: allow header row or no header.
        lines = [ln for ln in stripped.splitlines() if ln.strip()]
        detected["lines"] = len(lines)
        if not lines:
            return {"ok": False, "rows": 0, "errors": ["ไฟล์ว่าง"], "detected": detected}

        def split_parts(line: str) -> list:
            parts = [c.strip() for c in (line or "").split(delimiter)]
            # Support Markdown table style: | a | b | c |
            while parts and parts[0] == "":
                parts.pop(0)
            while parts and parts[-1] == "":
                parts.pop()
            return parts

        first = split_parts(lines[0])
        first_norm = [_normalize_header_key(c) for c in first]
        looks_like_header = any(k in _COURSE_HEADER_MAP for k in first_norm)
        detected["header_like"] = looks_like_header

        start_line_index = 1 if looks_like_header else 0
        for i, ln in enumerate(lines[start_line_index:], start=(2 if looks_like_header else 1)):
            parts = split_parts(ln)
            rows_total += 1
            if looks_like_header:
                row = {first[j]: (parts[j] if j < len(parts) else "") for j in range(len(first))}
                n = normalize_row(row)
                code = (n.get("code") or "").strip()
                name_th = (n.get("name_th") or "").strip()
                if not code or not name_th:
                    errors.append(f"บรรทัด {i}: ต้องมีรหัสวิชา (code) และชื่อวิชา (name_th)")
                else:
                    rows_ok += 1
            else:
                code = parts[0] if len(parts) > 0 else ""
                name_th = parts[1] if len(parts) > 1 else ""
                if not code or not name_th:
                    errors.append(f"บรรทัด {i}: รูปแบบต้องเป็น code{delimiter}name_th{delimiter}credits(optional){delimiter}name_en(optional)")
                else:
                    rows_ok += 1

        if rows_total == 0:
            errors.append("ไม่พบข้อมูลรายวิชาในไฟล์")

    ok = rows_total > 0 and rows_ok == rows_total
    return {
        "ok": ok,
        "rows": rows_total,
        "rows_ok": rows_ok,
        "errors": errors,
        "detected": detected,
    }


def _utcnow() -> datetime:
    return datetime.utcnow()


def get_active_role():
    if not current_user.is_authenticated:
        return None

    available = current_user.role_names()
    chosen = session.get("active_role")
    if chosen in available:
        return chosen

    if session.get("choose_role") and len(available) > 1:
        return None

    best = current_user.best_role()
    session["active_role"] = best
    session.pop("choose_role", None)
    return best


def _safe_redirect_next(default_endpoint: str, **default_kwargs):
    next_url = (request.form.get("next") or request.args.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **default_kwargs))


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if (not current_user.is_authenticated) or (not current_user.has_any_role(roles)):
                flash("คุณไม่มีสิทธิ์เข้าถึงหน้านี้", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


@app.context_processor
def _inject_roles_context():
    if not current_user.is_authenticated:
        return {}
    return {
        "active_role": get_active_role(),
        "available_roles": current_user.role_names(),
    }


@login_manager.user_loader
def load_user(user_id: str):
    return User.get(user_id)


def _get_or_404(model_cls, doc_id: str):
    obj = model_cls.get(doc_id)
    if not obj:
        abort(404)
    return obj


def _is_system_locked() -> bool:
    sections = Section.find_all()
    has_active = any(getattr(s, "status", "") == "active" for s in sections)
    has_locked = any(getattr(s, "status", "") == "locked" for s in sections)
    return (not has_active) and has_locked


def users_with_role(role_name: str):
    users = User.find_all()
    return [u for u in users if u.has_role(role_name)]


# --- Routes ---


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_raw = request.form.get("username") or ""
        username = username_raw.strip()
        password = request.form.get("password") or ""

        user = User.get_by_username(username) or User.get_by_username(username_raw)
        if user and user.check_password(password):
            login_user(user)
            roles = user.role_names()
            if len(roles) > 1:
                session.pop("active_role", None)
                session["choose_role"] = True
                return redirect(url_for("choose_role"))
            session["active_role"] = user.best_role()
            session.pop("choose_role", None)
            return redirect(url_for("dashboard"))

        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.pop("active_role", None)
    session.pop("choose_role", None)
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    role = get_active_role()
    if role is None:
        return redirect(url_for("choose_role"))
    if role == "instructor":
        return redirect(url_for("instructor_dashboard"))
    if role == "head":
        return redirect(url_for("head_dashboard"))
    if role == "academic":
        return redirect(url_for("academic_dashboard"))
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    return "Unknown Role"


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not current_user.check_password(current_password):
            flash("รหัสผ่านปัจจุบันไม่ถูกต้อง", "danger")
            return redirect(url_for("account"))

        if len(new_password) < 6:
            flash("รหัสผ่านใหม่ต้องมีอย่างน้อย 6 ตัวอักษร", "danger")
            return redirect(url_for("account"))

        if new_password != confirm_password:
            flash("ยืนยันรหัสผ่านใหม่ไม่ตรงกัน", "danger")
            return redirect(url_for("account"))

        user = _get_or_404(User, current_user.id)
        user.password_hash = generate_password_hash(new_password)
        user.save()
        flash("เปลี่ยนรหัสผ่านเรียบร้อย", "success")
        return redirect(url_for("account"))

    return render_template("account.html")


@app.route("/choose-role", methods=["GET", "POST"])
@login_required
def choose_role():
    roles = current_user.role_names()
    if len(roles) <= 1:
        session["active_role"] = current_user.best_role()
        session.pop("choose_role", None)
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        role = request.form.get("role")
        if role and current_user.has_role(role):
            session["active_role"] = role
            session.pop("choose_role", None)
            flash("เลือกบทบาทเรียบร้อย", "success")
            return redirect(url_for("dashboard"))
        flash("กรุณาเลือกบทบาทที่ถูกต้อง", "danger")

    return render_template("choose_role.html", roles=roles)


@app.route("/switch-role", methods=["POST"])
@login_required
def switch_role():
    role = request.form.get("role")
    if role and current_user.has_role(role):
        session["active_role"] = role
        session.pop("choose_role", None)
        flash(f"สลับบทบาทเป็น {role} แล้ว", "success")
    else:
        flash("ไม่สามารถสลับบทบาทได้", "danger")
    return redirect(url_for("dashboard"))


# --- Instructor ---


@app.route("/instructor/dashboard")
@login_required
@roles_required("instructor")
def instructor_dashboard():
    selected_term_id = request.args.get("term_id")

    sections = Section.find_by("instructor_id", current_user.id)
    if selected_term_id:
        sections = [s for s in sections if s.term_id == selected_term_id]

    term_ids = {s.term_id for s in sections if s.term_id}
    terms = [t for t in (Term.get(tid) for tid in term_ids) if t]
    terms.sort(key=lambda t: (t.year, t.semester), reverse=True)

    term_by_id = {t.id: t for t in terms}
    course_ids = {s.course_id for s in sections if s.course_id}
    courses = [c for c in (Course.get(cid) for cid in course_ids) if c]
    course_by_id = {c.id: c for c in courses}

    # Attach for templates
    for s in sections:
        s.term = term_by_id.get(s.term_id)
        s.course = course_by_id.get(s.course_id)

    # Attach TQF docs for templates (status / links)
    tqf3_docs = TQF3.find_all()
    tqf5_docs = TQF5.find_all()
    tqf3_by_section = {d.section_id: d for d in tqf3_docs if d.section_id}
    tqf5_by_section = {d.section_id: d for d in tqf5_docs if d.section_id}
    for s in sections:
        s.tqf3 = tqf3_by_section.get(s.id)
        s.tqf5 = tqf5_by_section.get(s.id)

    def _section_sort_key(sec: Section):
        t = term_by_id.get(sec.term_id)
        return (
            -(t.year if t else 0),
            -(t.semester if t else 0),
            sec.course.code if sec.course else "",
            sec.section_number or "",
        )

    sections.sort(key=_section_sort_key)

    return render_template(
        "instructor/dashboard.html",
        sections=sections,
        terms=terms,
        selected_term_id=selected_term_id,
    )


@app.route("/instructor/tqf3/<section_id>", methods=["GET", "POST"])
@login_required
@roles_required("instructor")
def edit_tqf3(section_id):
    section = _get_or_404(Section, section_id)
    if section.instructor_id != current_user.id:
        flash("คุณไม่มีสิทธิ์เข้าถึงรายวิชานี้", "danger")
        return redirect(url_for("dashboard"))

    if section.status == "locked":
        flash("ระบบถูกล็อกแล้ว ไม่สามารถแก้ไขเอกสารได้", "warning")
        return redirect(url_for("instructor_dashboard"))

    term = Term.get(section.term_id) if section.term_id else None
    if (not term) or (not bool(term.is_open_tqf3)):
        flash("เทอมนี้ยังไม่เปิดให้กรอก มคอ.3", "warning")
        return redirect(url_for("instructor_dashboard"))

    tqf3 = TQF3.first_by("section_id", section_id)
    if not tqf3:
        tqf3 = TQF3(section_id=section_id).save()

    if request.method == "POST":
        if tqf3.status in ["SUBMITTED", "APPROVED"]:
            flash("เอกสารถูกล็อกแล้ว ไม่สามารถแก้ไขได้", "warning")
            return redirect(url_for("instructor_dashboard"))

        data = {}
        for key in request.form.keys():
            if key.endswith("[]"):
                data[key] = request.form.getlist(key)
            else:
                if key != "action":
                    data[key] = request.form.get(key)

        tqf3.general_info = data

        action = request.form.get("action")
        if action == "submit":
            tqf3.status = "SUBMITTED"
            tqf3.submitted_at = _utcnow()
            flash("ส่ง มคอ.3 ให้หัวหน้าสาขาเรียบร้อยแล้ว", "success")
        else:
            tqf3.status = "DRAFT" if tqf3.status == "RETURNED" else tqf3.status
            flash("บันทึกร่าง มคอ.3 สำเร็จ", "success")

        tqf3.save()
        return redirect(url_for("instructor_dashboard"))

    feedbacks = [f for f in Feedback.find_by("tqf_id", tqf3.id) if f.tqf_type == "TQF3"]
    feedbacks.sort(key=lambda f: f.created_at, reverse=True)

    return render_template(
        "instructor/edit_tqf3.html",
        section=section,
        tqf3=tqf3,
        feedbacks=feedbacks,
    )


@app.route("/instructor/tqf5/<section_id>", methods=["GET", "POST"])
@login_required
@roles_required("instructor")
def edit_tqf5(section_id):
    section = _get_or_404(Section, section_id)
    if section.instructor_id != current_user.id:
        flash("คุณไม่มีสิทธิ์เข้าถึงรายวิชานี้", "danger")
        return redirect(url_for("dashboard"))

    if section.status == "locked":
        flash("ระบบถูกล็อกแล้ว ไม่สามารถแก้ไขเอกสารได้", "warning")
        return redirect(url_for("instructor_dashboard"))

    term = Term.get(section.term_id) if section.term_id else None
    if (not term) or (not bool(term.is_open_tqf5)):
        flash("เทอมนี้ยังไม่เปิดให้กรอก มคอ.5", "warning")
        return redirect(url_for("instructor_dashboard"))

    tqf3 = TQF3.first_by("section_id", section_id)
    if not tqf3:
        flash("กรุณาจัดทำ มคอ.3 ให้เรียบร้อยก่อนจัดทำ มคอ.5", "warning")
        return redirect(url_for("instructor_dashboard"))

    if tqf3.status != "APPROVED":
        flash("ยังไม่สามารถจัดทำ มคอ.5 ได้ (มคอ.3 ยังไม่อนุมัติ)", "warning")
        return redirect(url_for("instructor_dashboard"))

    tqf5 = TQF5.first_by("section_id", section_id)
    if not tqf5:
        tqf5 = TQF5(section_id=section_id, tqf3_id=tqf3.id).save()

    if request.method == "POST":
        if tqf5.status in ["SUBMITTED", "APPROVED"]:
            flash("เอกสารถูกล็อกแล้ว ไม่สามารถแก้ไขได้", "warning")
            return redirect(url_for("instructor_dashboard"))

        data = {}
        for key in request.form.keys():
            if key.endswith("[]"):
                data[key] = request.form.getlist(key)
            else:
                if key != "action":
                    data[key] = request.form.get(key)

        tqf5.actual_teaching = data

        action = request.form.get("action")
        if action == "submit":
            tqf5.status = "SUBMITTED"
            tqf5.submitted_at = _utcnow()
            flash("ส่ง มคอ.5 ให้หัวหน้าสาขาเรียบร้อยแล้ว", "success")
        else:
            tqf5.status = "DRAFT" if tqf5.status == "RETURNED" else tqf5.status
            flash("บันทึกร่าง มคอ.5 สำเร็จ", "success")

        tqf5.save()
        return redirect(url_for("instructor_dashboard"))

    feedbacks = [f for f in Feedback.find_by("tqf_id", tqf5.id) if f.tqf_type == "TQF5"]
    feedbacks.sort(key=lambda f: f.created_at, reverse=True)

    return render_template(
        "instructor/edit_tqf5.html",
        section=section,
        tqf5=tqf5,
        tqf3=tqf3,
        feedbacks=feedbacks,
    )


# --- Head ---


@app.route("/head/dashboard")
@login_required
@roles_required("head")
def head_dashboard():
    selected_term_id = (request.args.get("term_id") or "").strip()

    # Head belongs to a department (สาขา) which may have multiple programs.
    program_ids = set()
    if current_user.department_id:
        program_ids = {p.id for p in Program.find_by("department_id", current_user.department_id) if p.id}
    elif current_user.program_id:
        program_ids = {current_user.program_id}

    if not program_ids:
        return render_template(
            "head/dashboard.html",
            sections=[],
            instructors=[],
            terms=[],
            selected_term_id=selected_term_id,
        )

    sections = Section.find_all()
    course_ids = {s.course_id for s in sections if s.course_id}
    courses = [c for c in (Course.get(cid) for cid in course_ids) if c]
    course_by_id = {c.id: c for c in courses}

    filtered = []
    for s in sections:
        c = course_by_id.get(s.course_id)
        if not c:
            continue
        if c.program_id in program_ids:
            s.course = c
            filtered.append(s)

    term_ids = {s.term_id for s in filtered if s.term_id}
    terms = [t for t in (Term.get(tid) for tid in term_ids) if t]
    term_by_id = {t.id: t for t in terms if t.id}
    for s in filtered:
        s.term = term_by_id.get(s.term_id)

    if selected_term_id:
        filtered = [s for s in filtered if s.term_id == selected_term_id]

    # Attach TQF docs for templates (status / review links)
    tqf3_docs = TQF3.find_all()
    tqf5_docs = TQF5.find_all()
    tqf3_by_section = {d.section_id: d for d in tqf3_docs if d.section_id}
    tqf5_by_section = {d.section_id: d for d in tqf5_docs if d.section_id}
    for s in filtered:
        s.tqf3 = tqf3_by_section.get(s.id)
        s.tqf5 = tqf5_by_section.get(s.id)

    all_instructors = users_with_role("instructor")
    if current_user.department_id:
        instructors = [u for u in all_instructors if (u.department_id == current_user.department_id) or (u.program_id in program_ids)]
    else:
        instructors = [u for u in all_instructors if u.program_id in program_ids]
    instructors.sort(key=lambda u: u.full_name)

    all_terms = Term.find_all()
    all_terms.sort(key=lambda t: (t.year, t.semester), reverse=True)

    return render_template(
        "head/dashboard.html",
        sections=filtered,
        instructors=instructors,
        terms=all_terms,
        selected_term_id=selected_term_id,
    )


def _attach_section_context_to_tqf_doc(tqf: object) -> None:
    """Attach `section`, `course`, `term`, `instructor` runtime attributes for templates."""
    section_id = getattr(tqf, "section_id", None)
    if not section_id:
        return
    section = Section.get(section_id)
    if not section:
        return
    section.course = Course.get(section.course_id) if section.course_id else None
    section.term = Term.get(section.term_id) if section.term_id else None
    section.instructor = User.get(section.instructor_id) if section.instructor_id else None
    setattr(tqf, "section", section)


def _pretty_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _build_tqf_full_parts(tqf_type: str, tqf: object) -> list[dict]:
    if tqf_type == "tqf3":
        parts = [
            ("ข้อมูลทั่วไป (general_info)", getattr(tqf, "general_info", {}) or {}),
            ("CLO-PLO Mapping (clo_plo_mapping)", getattr(tqf, "clo_plo_mapping", {}) or {}),
            ("แผนการสอน (teaching_plan)", getattr(tqf, "teaching_plan", {}) or {}),
            ("แผนการประเมิน (evaluation_plan)", getattr(tqf, "evaluation_plan", {}) or {}),
        ]
    else:
        parts = [
            ("การสอนจริง (actual_teaching)", getattr(tqf, "actual_teaching", {}) or {}),
            ("สรุปผลการประเมิน (grade_distribution)", getattr(tqf, "grade_distribution", {}) or {}),
            ("การปรับปรุง/พัฒนา (improvements)", getattr(tqf, "improvements", {}) or {}),
            ("ผลการทวนสอบ (verification_result)", getattr(tqf, "verification_result", {}) or {}),
        ]

    return [{"title": title, "pretty": _pretty_json(data)} for title, data in parts]


@app.route("/head/review/<tqf_type>/<tqf_id>", methods=["GET", "POST"])
@login_required
@roles_required("head")
def review_tqf(tqf_type, tqf_id):
    if tqf_type == "tqf3":
        tqf = _get_or_404(TQF3, tqf_id)
        type_label = "TQF3"
    else:
        tqf = _get_or_404(TQF5, tqf_id)
        type_label = "TQF5"

    _attach_section_context_to_tqf_doc(tqf)

    if request.method == "POST":
        action = request.form.get("action")
        comment = request.form.get("comment") or ""

        tqf.status = "APPROVED" if action == "approve" else "RETURNED"
        if action == "approve":
            tqf.submitted_at = _utcnow()
        tqf.save()

        Feedback(
            tqf_type=type_label,
            tqf_id=tqf.id,
            reviewer_id=current_user.id,
            comment=comment,
        ).save()

        flash(f"ดำเนินการเรียบร้อย: {tqf.status}", "success")
        return redirect(url_for("head_dashboard"))

    return render_template(
        "head/review.html",
        tqf=tqf,
        tqf_type=tqf_type,
        full_parts=_build_tqf_full_parts(tqf_type, tqf),
        can_review=True,
        back_url=url_for("head_dashboard"),
        back_label="Dashboard",
    )


# --- Admin ---


@app.route("/admin/dashboard")
@login_required
@roles_required("admin")
def admin_dashboard():
    return render_template("admin/dashboard.html")


@app.route("/admin/faculties", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def manage_faculties():
    if request.method == "POST":
        action = (request.form.get("action") or "add_faculty").strip()

        if action in {"add_department", "add_program"}:
            faculty_id = (request.form.get("faculty_id") or "").strip()
            department_name = (request.form.get("department_name") or request.form.get("program_name") or "").strip()

            faculty = Faculty.get(faculty_id) if faculty_id else None
            if not faculty:
                flash("กรุณาเลือกคณะให้ถูกต้อง", "danger")
            elif not department_name:
                flash("กรุณากรอกชื่อสาขาวิชา", "danger")
            else:
                existing = [d for d in Department.find_by("faculty_id", faculty.id) if d.name == department_name]
                if existing:
                    flash("มีสาขาวิชานี้อยู่แล้ว", "info")
                else:
                    Department(name=department_name, faculty_id=faculty.id).save()
                    flash("เพิ่มสาขาวิชาเรียบร้อย", "success")

        else:
            name = (request.form.get("name") or "").strip()
            if name:
                existing = Faculty.first_by("name", name)
                if existing:
                    flash("มีคณะนี้อยู่แล้ว", "info")
                else:
                    Faculty(name=name).save()
                    flash("เพิ่มคณะเรียบร้อย", "success")

    faculties = Faculty.find_all()
    faculties.sort(key=lambda f: f.name)
    return render_template("admin/faculties.html", faculties=faculties)


@app.route("/admin/delete-faculty/<faculty_id>", methods=["POST"])
@login_required
@roles_required("admin")
def admin_delete_faculty(faculty_id):
    faculty = _get_or_404(Faculty, faculty_id)

    departments = Department.find_by("faculty_id", faculty.id)
    if departments:
        flash("ไม่สามารถลบคณะนี้ได้ เนื่องจากยังมีสาขาอยู่", "danger")
        return redirect(url_for("manage_faculties"))

    programs = Program.find_by("faculty_id", faculty.id)
    if programs:
        flash("ไม่สามารถลบคณะนี้ได้ เนื่องจากยังมีหลักสูตรอยู่", "danger")
        return redirect(url_for("manage_faculties"))

    users = User.find_by("faculty_id", faculty.id)
    if users:
        flash("ไม่สามารถลบคณะนี้ได้ เนื่องจากยังมีผู้ใช้สังกัดคณะนี้", "danger")
        return redirect(url_for("manage_faculties"))

    faculty.delete()
    flash("ลบคณะเรียบร้อยแล้ว", "success")
    return redirect(url_for("manage_faculties"))


@app.route("/admin/delete-department/<department_id>", methods=["POST"])
@login_required
@roles_required("admin")
def admin_delete_department(department_id):
    dept = _get_or_404(Department, department_id)

    programs = Program.find_by("department_id", dept.id)
    if programs:
        flash("ไม่สามารถลบสาขานี้ได้ เนื่องจากยังมีหลักสูตรอยู่ (กรุณาลบหลักสูตรก่อน)", "danger")
        return redirect(url_for("manage_faculties"))

    users = User.find_by("department_id", dept.id)
    if users:
        flash("ไม่สามารถลบสาขานี้ได้ เนื่องจากยังมีผู้ใช้สังกัดสาขานี้", "danger")
        return redirect(url_for("manage_faculties"))

    dept.delete()
    flash("ลบสาขาเรียบร้อยแล้ว", "success")
    return redirect(url_for("manage_faculties"))


def _handle_programs_request():
    if request.method == "POST":
        # Curriculum upload (file picker in the program list)
        upload = request.files.get("curriculum_text")
        upload_program_id = (request.form.get("program_id") or "").strip()
        if upload and getattr(upload, "filename", "") and upload.filename and upload_program_id:
            program = Program.get(upload_program_id)
            if not program:
                flash("ไม่พบหลักสูตรสำหรับอัปโหลดไฟล์", "danger")
            else:
                raw = upload.read() or b""
                size_bytes = len(raw)
                if size_bytes > 2_000_000:
                    flash("ไฟล์มีขนาดใหญ่เกินไป (จำกัด 2MB)", "danger")
                else:
                    try:
                        text = raw.decode("utf-8-sig")
                    except Exception:
                        text = raw.decode("utf-8", errors="replace")

                    filename = secure_filename(upload.filename) or upload.filename
                    validation = _validate_courses_upload_text(text, filename)
                    parsed = _parse_courses_upload_text(text, filename)

                    # This flow is import-only: do not store the uploaded file contents.
                    if validation.get("ok"):
                        parsed_courses = parsed.get("courses") or []
                        if not parsed.get("ok") or not parsed_courses:
                            flash(
                                f"ตรวจสอบไฟล์ผ่าน แต่ไม่สามารถแปลงข้อมูลรายวิชาได้ ({upload.filename})",
                                "danger",
                            )
                        else:
                            import_summary = _import_courses_into_program(program, parsed_courses)
                            flash(
                                f"ตรวจสอบไฟล์ผ่าน: พบ {validation.get('rows', 0)} รายวิชา ({upload.filename})",
                                "success",
                            )
                            flash(
                                "นำเข้ารายวิชาเรียบร้อย "
                                f"(เพิ่มใหม่ {import_summary.get('created', 0)}, "
                                f"อัปเดต {import_summary.get('updated', 0)}, "
                                f"ข้าม {import_summary.get('skipped', 0)})",
                                "success",
                            )
                    else:
                        errs = validation.get("errors") or []
                        short = " | ".join(errs[:3]) if errs else "รูปแบบไฟล์ไม่ถูกต้อง"
                        flash(
                            f"ตรวจสอบไฟล์ไม่ผ่าน ({upload.filename}): {short}",
                            "danger",
                        )

            # Post/Redirect/Get to avoid browser re-submission on refresh.
            return redirect(url_for(request.endpoint))

        name = (request.form.get("name") or "").strip()
        department_id = (request.form.get("department_id") or "").strip()
        year_raw = (request.form.get("year") or "").strip()
        year = None
        if year_raw:
            try:
                year = int(year_raw)
            except Exception:
                year = None

        if name and department_id:
            dept = Department.get(department_id)
            if not dept:
                flash("กรุณาเลือกสาขาวิชาให้ถูกต้อง", "danger")
            else:
                Program(
                    name=name,
                    department_id=dept.id,
                    faculty_id=dept.faculty_id,
                    year=year,
                ).save()
                flash("เพิ่มหลักสูตรเรียบร้อย", "success")

    faculties = Faculty.find_all()
    faculties.sort(key=lambda f: f.name)
    faculty_name_by_id = {f.id: f.name for f in faculties if f and f.id}

    departments = Department.find_all()
    # Avoid N+1 Firestore reads via Department.faculty property in sorting.
    departments.sort(key=lambda d: (faculty_name_by_id.get(d.faculty_id) or "", d.name))
    department_name_by_id = {d.id: d.name for d in departments if d and d.id}

    programs = Program.find_all()
    programs.sort(key=lambda p: (-(p.year or 0), p.name))

    # Pre-compute course counts per program to avoid N+1 queries in template (program.courses).
    program_ids = {p.id for p in programs if p and p.id}
    course_count_by_program_id = {}
    for c in Course.find_all():
        pid = c.program_id
        if not pid or pid not in program_ids:
            continue
        course_count_by_program_id[pid] = course_count_by_program_id.get(pid, 0) + 1

    return render_template(
        "admin/programs.html",
        faculties=faculties,
        departments=departments,
        programs=programs,
        faculty_name_by_id=faculty_name_by_id,
        department_name_by_id=department_name_by_id,
        course_count_by_program_id=course_count_by_program_id,
    )


@app.route("/admin/programs", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def admin_manage_programs():
    return _handle_programs_request()


@app.route("/academic/programs", methods=["GET", "POST"])
@login_required
@roles_required("academic", "admin")
def academic_manage_programs():
    return _handle_programs_request()


@app.route("/admin/delete-program/<program_id>", methods=["POST"])
@login_required
@roles_required("admin")
def admin_delete_program(program_id):
    program = _get_or_404(Program, program_id)
    courses = Course.find_by("program_id", program_id)

    deleted_term_programs = 0
    deleted_sections = 0
    deleted_tqf3 = 0
    deleted_tqf5 = 0
    deleted_feedback = 0
    deleted_courses = 0

    # Remove program-term relations
    term_programs = TermProgram.find_by("program_id", program_id)
    for tp in term_programs:
        tp.delete()
        deleted_term_programs += 1

    # Cascade delete sections/docs/feedback for every course in the program.
    course_ids = [c.id for c in courses if c.id]
    seen_section_ids = set()
    for cid in course_ids:
        for s in Section.find_by("course_id", cid):
            if not s.id or s.id in seen_section_ids:
                continue
            seen_section_ids.add(s.id)

            d3 = TQF3.first_by("section_id", s.id)
            if d3 and d3.id:
                for fb in Feedback.find_by("tqf_id", d3.id):
                    if fb.tqf_type == "TQF3":
                        fb.delete()
                        deleted_feedback += 1
                d3.delete()
                deleted_tqf3 += 1

            d5 = TQF5.first_by("section_id", s.id)
            if d5 and d5.id:
                for fb in Feedback.find_by("tqf_id", d5.id):
                    if fb.tqf_type == "TQF5":
                        fb.delete()
                        deleted_feedback += 1
                d5.delete()
                deleted_tqf5 += 1

            s.delete()
            deleted_sections += 1

    # Delete courses then the program.
    for c in courses:
        c.delete()
        deleted_courses += 1
    program.delete()

    flash(
        "ลบหลักสูตรเรียบร้อยแล้ว "
        f"(ลบความสัมพันธ์เทอม {deleted_term_programs}, "
        f"ลบ Section {deleted_sections}, "
        f"ลบ TQF3 {deleted_tqf3}, ลบ TQF5 {deleted_tqf5}, "
        f"ลบ Feedback {deleted_feedback}, "
        f"ลบรายวิชา {deleted_courses})",
        "success",
    )
    return redirect(url_for("admin_manage_programs"))


@app.route("/admin/courses", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def manage_courses():
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        name_th = (request.form.get("name_th") or "").strip()
        name_en = (request.form.get("name_en") or "").strip()
        credits = (request.form.get("credits") or "").strip() or None
        program_id = request.form.get("program_id") or None

        if code and name_th:
            Course(
                code=code,
                name_th=name_th,
                name_en=name_en or name_th,
                credits=credits,
                program_id=program_id,
            ).save()
            flash("เพิ่มรายวิชาเรียบร้อย", "success")

    programs = Program.find_all()
    programs.sort(key=lambda p: (p.name, p.year or 0))
    programs_by_id = {p.id: p for p in programs if p and p.id}

    selected_program_id = request.args.get("program_id")

    if selected_program_id:
        courses = Course.find_by("program_id", selected_program_id)
    else:
        courses = Course.find_all()

    grouped_courses = {}
    for course in courses:
        prog = programs_by_id.get(course.program_id) if course.program_id else None
        prog_name = prog.name if prog else "Other"
        if prog and prog.year:
            prog_name += f" ({prog.year})"
        grouped_courses.setdefault(prog_name, []).append(course)

    for k in grouped_courses:
        grouped_courses[k].sort(key=lambda c: c.code)

    return render_template(
        "admin/courses.html",
        grouped_courses=grouped_courses,
        programs=programs,
        selected_program_id=selected_program_id,
    )


@app.route("/admin/delete-course/<course_id>", methods=["POST"])
@login_required
@roles_required("admin")
def delete_course(course_id):
    course = _get_or_404(Course, course_id)
    if Section.first_by("course_id", course_id):
        flash("ไม่สามารถลบรายวิชานี้ได้ เนื่องจากมีการเปิดสอนในเทอมต่างๆ", "danger")
    else:
        course.delete()
        flash("ลบรายวิชาเรียบร้อยแล้ว", "success")
    return redirect(url_for("manage_courses"))


@app.route("/admin/users", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def manage_users():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip()
        roles = request.form.getlist("roles")
        faculty_id = request.form.get("faculty_id") or None
        department_id = request.form.get("department_id") or None
        program_id = request.form.get("program_id") or None

        if username and password:
            roles = [r for r in roles if r]
            roles = list(dict.fromkeys(roles))
            if not roles:
                flash("กรุณาเลือกบทบาทอย่างน้อย 1 บทบาท", "danger")
                return redirect(url_for("manage_users"))

            if User.get_by_username(username):
                flash("ไม่สามารถเพิ่มผู้ใช้ได้ (ชื่อผู้ใช้อาจซ้ำกัน)", "danger")
                return redirect(url_for("manage_users"))

            # If a program is selected, prefer its department/faculty.
            if program_id:
                prog = Program.get(program_id)
                if prog:
                    if prog.department_id:
                        department_id = prog.department_id
                    if prog.faculty_id:
                        faculty_id = prog.faculty_id

            # If a department is selected, prefer its faculty.
            if department_id and not faculty_id:
                dept = Department.get(department_id)
                if dept and dept.faculty_id:
                    faculty_id = dept.faculty_id

            user = User(
                id=username,
                username=username,
                password_hash=generate_password_hash(password),
                full_name=full_name,
                roles=roles,
                faculty_id=faculty_id,
                department_id=department_id,
                program_id=program_id,
            )
            user.save()
            flash("เพิ่มผู้ใช้เรียบร้อย", "success")

    users = User.find_all()
    users.sort(key=lambda u: u.username)

    faculties = Faculty.find_all()
    faculties.sort(key=lambda f: f.name)

    faculty_name_by_id = {f.id: f.name for f in faculties if f and f.id}

    departments = Department.find_all()
    # Avoid N+1 Firestore reads via Department.faculty property in sorting.
    departments.sort(key=lambda d: (faculty_name_by_id.get(d.faculty_id) or "", d.name))

    department_name_by_id = {d.id: d.name for d in departments if d and d.id}

    programs = Program.find_all()
    programs.sort(key=lambda p: (p.name, p.year or 0))

    program_label_by_id = {}
    for p in programs:
        if not p or not p.id:
            continue
        label = p.name
        if p.year:
            label += f" ({p.year})"
        program_label_by_id[p.id] = label

    # Affiliation label for display column, without triggering per-user Firestore lookups.
    user_affiliation_by_user_id = {}
    for u in users:
        if not u:
            continue
        label = "System"
        if u.program_id and u.program_id in program_label_by_id:
            label = program_label_by_id[u.program_id]
        elif u.department_id and u.department_id in department_name_by_id:
            label = department_name_by_id[u.department_id]
        elif u.faculty_id and u.faculty_id in faculty_name_by_id:
            label = faculty_name_by_id[u.faculty_id]
        user_affiliation_by_user_id[u.id] = label

    return render_template(
        "admin/users.html",
        users=users,
        faculties=faculties,
        departments=departments,
        programs=programs,
        faculty_name_by_id=faculty_name_by_id,
        department_name_by_id=department_name_by_id,
        program_label_by_id=program_label_by_id,
        user_affiliation_by_user_id=user_affiliation_by_user_id,
    )


@app.route("/admin/users/<user_id>/roles", methods=["POST"])
@login_required
@roles_required("admin")
def admin_update_user_roles(user_id):
    user = _get_or_404(User, user_id)
    roles = request.form.getlist("roles")
    roles = [r for r in roles if r]
    roles = list(dict.fromkeys(roles))
    if not roles:
        flash("กรุณาเลือกบทบาทอย่างน้อย 1 บทบาท", "danger")
        return redirect(url_for("manage_users"))

    user.roles = roles
    user.save()

    if current_user.id == user.id:
        session.pop("active_role", None)

    flash("อัปเดตบทบาทเรียบร้อย", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/users/<user_id>/affiliation", methods=["POST"])
@login_required
@roles_required("admin")
def admin_update_user_affiliation(user_id):
    user = _get_or_404(User, user_id)

    faculty_id = request.form.get("faculty_id") or None
    department_id = request.form.get("department_id") or None
    program_id = request.form.get("program_id") or None

    # If a program is selected, prefer its department/faculty.
    if program_id:
        prog = Program.get(program_id)
        if not prog:
            flash("ไม่พบหลักสูตรที่เลือก", "danger")
            return redirect(url_for("manage_users"))
        if prog.department_id:
            department_id = prog.department_id
        if prog.faculty_id:
            faculty_id = prog.faculty_id

    # If a department is selected, prefer its faculty.
    if department_id:
        dept = Department.get(department_id)
        if not dept:
            flash("ไม่พบสาขาที่เลือก", "danger")
            return redirect(url_for("manage_users"))
        if dept.faculty_id:
            faculty_id = dept.faculty_id

    user.faculty_id = faculty_id
    user.department_id = department_id
    user.program_id = program_id
    user.save()

    flash("อัปเดตสังกัดเรียบร้อย", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/delete-user/<user_id>", methods=["POST"])
@login_required
@roles_required("admin")
def admin_delete_user(user_id):
    user = _get_or_404(User, user_id)

    if current_user.is_authenticated and current_user.id == user.id:
        flash("ไม่สามารถลบบัญชีของตนเองได้", "danger")
        return redirect(url_for("manage_users"))

    if user.has_role("admin"):
        admins = [u for u in User.find_all() if u.has_role("admin")]
        if len(admins) <= 1:
            flash("ไม่สามารถลบผู้ดูแลระบบคนสุดท้ายได้", "danger")
            return redirect(url_for("manage_users"))

    # Unassign instructor from any sections to avoid dangling references.
    sections = Section.find_by("instructor_id", user.id)
    for s in sections:
        s.instructor_id = None
        s.save()

    user.delete()
    flash("ลบผู้ใช้เรียบร้อยแล้ว", "success")
    return redirect(url_for("manage_users"))


# --- Academic ---


@app.route("/academic/dashboard")
@login_required
@roles_required("academic")
def academic_dashboard():
    selected_term_id = request.args.get("term_id")
    all_terms = Term.find_all()
    all_terms.sort(key=lambda t: (t.year, t.semester), reverse=True)

    if selected_term_id:
        selected_term = Term.get(selected_term_id)
        terms = [selected_term] if selected_term else []
    else:
        terms = all_terms

    programs = Program.find_all()
    programs.sort(key=lambda p: (-(p.year or 0), p.name))
    programs_by_id = {p.id: p for p in programs}

    term_program_rows = TermProgram.find_all()
    term_program_ids = {}
    for tp in term_program_rows:
        term_program_ids.setdefault(tp.term_id, []).append(tp.program_id)

    grouped_data = {}
    for term in terms:
        if not term:
            continue
        term_label = f"{term.semester}/{term.year}"
        grouped_data[term_label] = {
            "term_id": term.id,
            "programs": {},
            "is_open_tqf3": bool(term.is_open_tqf3),
            "is_open_tqf5": bool(term.is_open_tqf5),
        }
        for prog_id in sorted(set(term_program_ids.get(term.id, []))):
            prog = programs_by_id.get(prog_id)
            if prog:
                grouped_data[term_label]["programs"][prog.id] = {"name": prog.name, "year": prog.year}

    sections = Section.find_all()
    total = len(sections)

    is_system_locked = _is_system_locked()

    tqf3_docs = TQF3.find_all()
    tqf5_docs = TQF5.find_all()
    tqf3_by_section = {d.section_id: d for d in tqf3_docs if d.section_id}
    tqf5_by_section = {d.section_id: d for d in tqf5_docs if d.section_id}

    if total > 0:
        tqf3_submitted = 0
        tqf3_approved = 0
        tqf5_submitted = 0
        tqf5_approved = 0

        for s in sections:
            d3 = tqf3_by_section.get(s.id)
            if d3 and d3.status in ["SUBMITTED", "APPROVED"]:
                tqf3_submitted += 1
            if d3 and d3.status == "APPROVED":
                tqf3_approved += 1

            d5 = tqf5_by_section.get(s.id)
            if d5 and d5.status in ["SUBMITTED", "APPROVED"]:
                tqf5_submitted += 1
            if d5 and d5.status == "APPROVED":
                tqf5_approved += 1

        stats = {
            "total": total,
            "tqf3_perc": round((tqf3_submitted / total) * 100),
            "tqf3_app_perc": round((tqf3_approved / total) * 100),
            "tqf5_perc": round((tqf5_submitted / total) * 100),
            "tqf5_app_perc": round((tqf5_approved / total) * 100),
        }
    else:
        stats = {"total": 0, "tqf3_perc": 0, "tqf3_app_perc": 0, "tqf5_perc": 0, "tqf5_app_perc": 0}

    return render_template(
        "academic/dashboard.html",
        grouped_data=grouped_data,
        stats=stats,
        is_system_locked=is_system_locked,
        programs=programs,
        term_program_ids=term_program_ids,
        terms=all_terms,
        selected_term_id=selected_term_id,
    )


@app.route("/academic/term/<term_id>/program/<program_id>")
@login_required
@roles_required("academic")
def academic_term_program(term_id, program_id):
    term = _get_or_404(Term, term_id)
    program = _get_or_404(Program, program_id)

    tp = None
    for row in TermProgram.find_by("term_id", term_id):
        if row.program_id == program_id:
            tp = row
            break

    if not tp:
        flash("หลักสูตรนี้ยังไม่ได้ถูกเพิ่มในเทอมนี้", "warning")
        return redirect(url_for("academic_dashboard"))

    is_system_locked = _is_system_locked()

    courses = Course.find_by("program_id", program_id)
    courses.sort(key=lambda c: c.code)
    course_by_id = {c.id: c for c in courses}

    sections = [s for s in Section.find_by("term_id", term_id) if s.course_id in course_by_id]
    for s in sections:
        s.course = course_by_id.get(s.course_id)

    tqf3_docs = TQF3.find_all()
    tqf5_docs = TQF5.find_all()
    tqf3_by_section = {d.section_id: d for d in tqf3_docs if d.section_id}
    tqf5_by_section = {d.section_id: d for d in tqf5_docs if d.section_id}
    for s in sections:
        s.tqf3 = tqf3_by_section.get(s.id)
        s.tqf5 = tqf5_by_section.get(s.id)

    def _sec_key(s: Section):
        return (s.course.code if s.course else "", s.section_number or "")

    sections.sort(key=_sec_key)

    instructors = [u for u in users_with_role("instructor")]
    instructors.sort(key=lambda u: u.full_name)
    instructor_by_id = {u.id: u for u in instructors if u.id}
    for s in sections:
        # Runtime attach for templates
        s.instructor = instructor_by_id.get(s.instructor_id)

    courses_grouped = {}
    for s in sections:
        label = f"{s.course.code} - {s.course.name_th}" if s.course else ""
        courses_grouped.setdefault(label, []).append(s)

    return render_template(
        "academic/term_program.html",
        term=term,
        program=program,
        courses=courses,
        courses_grouped=courses_grouped,
        instructors=instructors,
        is_system_locked=is_system_locked,
    )


@app.route("/academic/term/<term_id>/documents")
@login_required
@roles_required("academic")
def academic_term_documents(term_id):
    term = _get_or_404(Term, term_id)

    selected_program_id = (request.args.get("program_id") or "").strip()

    sections = Section.find_by("term_id", term_id)
    course_ids = {s.course_id for s in sections if s.course_id}
    courses = [c for c in (Course.get(cid) for cid in course_ids) if c]
    course_by_id = {c.id: c for c in courses if c.id}

    program_ids = {c.program_id for c in courses if c.program_id}
    programs = [p for p in (Program.get(pid) for pid in program_ids) if p]
    programs.sort(key=lambda p: (-(p.year or 0), p.name))
    program_by_id = {p.id: p for p in programs if p.id}

    instructors = users_with_role("instructor")
    instructor_by_id = {u.id: u for u in instructors if u.id}

    tqf3_docs = TQF3.find_all()
    tqf5_docs = TQF5.find_all()
    tqf3_by_section = {d.section_id: d for d in tqf3_docs if d.section_id}
    tqf5_by_section = {d.section_id: d for d in tqf5_docs if d.section_id}

    rows = []
    for s in sections:
        s.course = course_by_id.get(s.course_id)
        s.term = term
        s.instructor = instructor_by_id.get(s.instructor_id)
        s.tqf3 = tqf3_by_section.get(s.id)
        s.tqf5 = tqf5_by_section.get(s.id)
        prog = program_by_id.get(s.course.program_id) if (s.course and s.course.program_id) else None
        setattr(s, "program", prog)
        if selected_program_id and (not prog or prog.id != selected_program_id):
            continue
        rows.append(s)

    def _row_key(sec: Section):
        prog = getattr(sec, "program", None)
        prog_name = prog.name if prog else ""
        course_code = sec.course.code if sec.course else ""
        return (prog_name, course_code, sec.section_number or "")

    rows.sort(key=_row_key)

    total = len(rows)
    tqf3_submitted = sum(1 for s in rows if s.tqf3 and s.tqf3.status in ["SUBMITTED", "APPROVED"])
    tqf3_approved = sum(1 for s in rows if s.tqf3 and s.tqf3.status == "APPROVED")
    tqf5_submitted = sum(1 for s in rows if s.tqf5 and s.tqf5.status in ["SUBMITTED", "APPROVED"])
    tqf5_approved = sum(1 for s in rows if s.tqf5 and s.tqf5.status == "APPROVED")

    return render_template(
        "academic/term_documents.html",
        term=term,
        sections=rows,
        programs=programs,
        selected_program_id=selected_program_id,
        stats={
            "total": total,
            "tqf3_submitted": tqf3_submitted,
            "tqf3_approved": tqf3_approved,
            "tqf5_submitted": tqf5_submitted,
            "tqf5_approved": tqf5_approved,
        },
        is_system_locked=_is_system_locked(),
    )


@app.route("/head/term/<term_id>/documents")
@login_required
@roles_required("head")
def head_term_documents(term_id):
    term = _get_or_404(Term, term_id)

    # Head belongs to a department (สาขา) which may have multiple programs.
    program_ids = set()
    if current_user.department_id:
        program_ids = {p.id for p in Program.find_by("department_id", current_user.department_id) if p.id}
    elif current_user.program_id:
        program_ids = {current_user.program_id}

    if not program_ids:
        return render_template(
            "head/term_documents.html",
            term=term,
            sections=[],
            stats={"total": 0, "tqf3_submitted": 0, "tqf3_approved": 0, "tqf5_submitted": 0, "tqf5_approved": 0},
        )

    sections = Section.find_by("term_id", term_id)
    course_ids = {s.course_id for s in sections if s.course_id}
    courses = [c for c in (Course.get(cid) for cid in course_ids) if c]
    course_by_id = {c.id: c for c in courses if c.id}

    instructors = users_with_role("instructor")
    instructor_by_id = {u.id: u for u in instructors if u.id}

    tqf3_docs = TQF3.find_all()
    tqf5_docs = TQF5.find_all()
    tqf3_by_section = {d.section_id: d for d in tqf3_docs if d.section_id}
    tqf5_by_section = {d.section_id: d for d in tqf5_docs if d.section_id}

    rows = []
    for s in sections:
        c = course_by_id.get(s.course_id)
        if not c or not c.program_id or (c.program_id not in program_ids):
            continue
        s.course = c
        s.term = term
        s.instructor = instructor_by_id.get(s.instructor_id)
        s.tqf3 = tqf3_by_section.get(s.id)
        s.tqf5 = tqf5_by_section.get(s.id)
        rows.append(s)

    def _row_key(sec: Section):
        course_code = sec.course.code if sec.course else ""
        return (course_code, sec.section_number or "")

    rows.sort(key=_row_key)

    total = len(rows)
    tqf3_submitted = sum(1 for s in rows if s.tqf3 and s.tqf3.status in ["SUBMITTED", "APPROVED"])
    tqf3_approved = sum(1 for s in rows if s.tqf3 and s.tqf3.status == "APPROVED")
    tqf5_submitted = sum(1 for s in rows if s.tqf5 and s.tqf5.status in ["SUBMITTED", "APPROVED"])
    tqf5_approved = sum(1 for s in rows if s.tqf5 and s.tqf5.status == "APPROVED")

    return render_template(
        "head/term_documents.html",
        term=term,
        sections=rows,
        stats={
            "total": total,
            "tqf3_submitted": tqf3_submitted,
            "tqf3_approved": tqf3_approved,
            "tqf5_submitted": tqf5_submitted,
            "tqf5_approved": tqf5_approved,
        },
    )


@app.route("/academic/view/<tqf_type>/<tqf_id>")
@login_required
@roles_required("academic")
def academic_view_tqf(tqf_type, tqf_id):
    if tqf_type == "tqf3":
        tqf = _get_or_404(TQF3, tqf_id)
    else:
        tqf = _get_or_404(TQF5, tqf_id)

    _attach_section_context_to_tqf_doc(tqf)

    back_url_raw = (request.args.get("next") or "").strip()
    back_url = back_url_raw if back_url_raw.startswith("/") else url_for("academic_dashboard")
    return render_template(
        "head/review.html",
        tqf=tqf,
        tqf_type=tqf_type,
        full_parts=_build_tqf_full_parts(tqf_type, tqf),
        can_review=False,
        back_url=back_url,
        back_label="กลับ",
    )


@app.route("/academic/add-program-to-term", methods=["POST"])
@login_required
@roles_required("academic")
def academic_add_program_to_term():
    term_id = request.form.get("term_id")
    program_id = request.form.get("program_id")
    if not term_id or not program_id:
        flash("ข้อมูลไม่ครบถ้วน", "danger")
        return redirect(url_for("academic_dashboard"))

    if _is_system_locked():
        flash("ระบบถูกล็อกอยู่ ไม่สามารถเพิ่มหลักสูตรในเทอมได้", "warning")
        return redirect(url_for("academic_dashboard"))

    term = _get_or_404(Term, term_id)
    program = _get_or_404(Program, program_id)

    exists = any(tp.program_id == program_id for tp in TermProgram.find_by("term_id", term_id))
    if exists:
        flash("หลักสูตรนี้ถูกเพิ่มในเทอมนี้แล้ว", "info")
        return redirect(url_for("academic_dashboard"))

    TermProgram(term_id=term_id, program_id=program_id, created_at=_utcnow()).save()
    flash(f"เพิ่มหลักสูตร {program.name} ({program.year}) ในปีการศึกษา {term.semester}/{term.year} แล้ว", "success")
    return redirect(url_for("academic_dashboard"))


@app.route("/academic/bulk-open-courses", methods=["POST"])
@login_required
@roles_required("academic")
def academic_bulk_open_courses():
    term_id = request.form.get("term_id")
    program_id = request.form.get("program_id")
    section_number = (request.form.get("section_number") or "1").strip()
    course_ids = request.form.getlist("course_ids")

    if _is_system_locked():
        flash("ระบบถูกล็อกอยู่ ไม่สามารถเปิดรายวิชาเพิ่มได้", "warning")
        return redirect(url_for("academic_dashboard"))

    if not term_id or not program_id or not course_ids:
        flash("กรุณาเลือกอย่างน้อย 1 รายวิชา", "danger")
        return redirect(url_for("academic_dashboard"))

    term = _get_or_404(Term, term_id)
    program = _get_or_404(Program, program_id)

    if not any(tp.program_id == program_id for tp in TermProgram.find_by("term_id", term_id)):
        TermProgram(term_id=term_id, program_id=program_id, created_at=_utcnow()).save()

    existing_sections = Section.find_by("term_id", term_id)

    created = 0
    skipped = 0
    for cid in course_ids:
        course = Course.get(cid)
        if not course or course.program_id != program_id:
            skipped += 1
            continue

        dup = any(
            s.course_id == cid and (s.section_number or "") == section_number for s in existing_sections
        )
        if dup:
            skipped += 1
            continue

        Section(
            course_id=cid,
            term_id=term_id,
            section_number=section_number,
            instructor_id=None,
            is_open=False,
            status="active",
        ).save()
        created += 1

    flash(f"เพิ่มรายวิชาเปิดสอนแล้ว: สร้าง {created} รายการ, ข้าม {skipped} รายการ (ซ้ำ/ไม่ถูกต้อง)", "success")
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/remove-program-from-term", methods=["POST"])
@login_required
@roles_required("academic")
def academic_remove_program_from_term():
    term_id = request.form.get("term_id")
    program_id = request.form.get("program_id")
    if not term_id or not program_id:
        flash("ข้อมูลไม่ครบถ้วน", "danger")
        return redirect(url_for("academic_dashboard"))

    if _is_system_locked():
        flash("ระบบถูกล็อกอยู่ ไม่สามารถลบหลักสูตรออกจากเทอมได้", "warning")
        return redirect(url_for("academic_dashboard"))

    term = _get_or_404(Term, term_id)
    program = _get_or_404(Program, program_id)

    # Block removal if there are already opened sections for this term + program
    courses = Course.find_by("program_id", program_id)
    course_ids = {c.id for c in courses if c.id}
    if any(s.course_id in course_ids for s in Section.find_by("term_id", term_id)):
        flash("ลบหลักสูตรออกจากเทอมนี้ไม่ได้ เพราะมีรายวิชาที่เปิดสอนแล้ว (ให้ลบรายวิชาเปิดสอนก่อน)", "danger")
        return redirect(url_for("academic_dashboard"))

    tp_rows = TermProgram.find_by("term_id", term_id)
    tp = next((row for row in tp_rows if row.program_id == program_id), None)
    if not tp:
        flash("ไม่พบหลักสูตรนี้ในเทอมดังกล่าว", "info")
        return redirect(url_for("academic_dashboard"))

    tp.delete()
    flash(f"ลบหลักสูตร {program.name} ({program.year}) ออกจากปีการศึกษา {term.semester}/{term.year} แล้ว", "success")
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/manage-terms", methods=["GET", "POST"])
@login_required
@roles_required("academic", "admin")
def manage_terms():
    if request.method == "POST":
        year = (request.form.get("year") or "").strip()
        semester = (request.form.get("semester") or "").strip()
        if year and semester:
            try:
                Term(year=int(year), semester=int(semester)).save()
                flash("เพิ่มปีการศึกษา/ภาคเรียนเรียบร้อย", "success")
            except Exception:
                flash("ข้อมูลปีการศึกษา/ภาคเรียนไม่ถูกต้อง", "danger")

    terms = Term.find_all()
    terms.sort(key=lambda t: (t.year, t.semester), reverse=True)
    return render_template("academic/manage_terms.html", terms=terms)


@app.route("/academic/delete-term/<term_id>", methods=["POST"])
@login_required
@roles_required("academic", "admin")
def delete_term(term_id):
    term = _get_or_404(Term, term_id)

    if Section.first_by("term_id", term_id):
        flash("ไม่สามารถลบปีการศึกษานี้ได้ เนื่องจากมีการเปิดรายวิชาสอนแล้ว", "danger")
    else:
        term.delete()
        flash("ลบปีการศึกษาเรียบร้อยแล้ว", "success")
    return redirect(url_for("manage_terms"))


@app.route("/academic/lock-term", methods=["POST"])
@login_required
@roles_required("academic")
def lock_term():
    terms = Term.find_all()
    for t in terms:
        t.is_open_tqf3 = False
        t.is_open_tqf5 = False
        t.save()

    sections = Section.find_all()
    for s in sections:
        if s.status == "active":
            s.status = "locked"
            s.is_open = False
            s.is_open_tqf5 = False
            s.save()
    flash("ทำการปิดรอบและล็อกเอกสารเรียบร้อยแล้ว", "warning")
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/unlock-term", methods=["POST"])
@login_required
@roles_required("academic")
def unlock_term():
    terms = Term.find_all()
    for t in terms:
        t.is_open_tqf3 = False
        t.is_open_tqf5 = False
        t.save()

    sections = Section.find_all()
    for s in sections:
        if s.status in ["active", "locked"]:
            s.status = "active"
            s.is_open = False
            s.is_open_tqf5 = False
            s.save()
    flash("ทำการเปิดรอบและปลดล็อกเอกสารเรียบร้อยแล้ว", "success")
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/open-course", methods=["GET", "POST"])
@login_required
@roles_required("academic")
def open_course():
    if request.method == "POST":
        if _is_system_locked():
            flash("ระบบถูกล็อกอยู่ ไม่สามารถเปิดรายวิชาเพิ่มได้", "warning")
            return redirect(url_for("academic_dashboard"))

        course_id = request.form.get("course_id")
        term_id = request.form.get("term_id")
        section_number = (request.form.get("section_number") or "1").strip()

        if course_id and term_id:
            course = Course.get(course_id)
            if course and course.program_id:
                if not any(tp.program_id == course.program_id for tp in TermProgram.find_by("term_id", term_id)):
                    TermProgram(term_id=term_id, program_id=course.program_id, created_at=_utcnow()).save()

            existing = [
                s
                for s in Section.find_by("term_id", term_id)
                if s.course_id == course_id and (s.section_number or "") == section_number
            ]
            if existing:
                flash("มีการเปิดรายวิชานี้ (หมู่เรียนนี้) แล้วในเทอมดังกล่าว", "warning")
                return redirect(url_for("academic_dashboard"))

            Section(
                course_id=course_id,
                term_id=term_id,
                section_number=section_number,
                instructor_id=None,
                is_open=False,
                status="active",
            ).save()
            flash("เปิดรายวิชาสอนเรียบร้อย (รอหัวหน้าสาขามอบหมายผู้สอน)", "success")
            return _safe_redirect_next("academic_dashboard")

    courses = Course.find_all()
    terms = Term.find_all()
    terms.sort(key=lambda t: (t.year, t.semester), reverse=True)

    instructors = users_with_role("instructor")
    instructors.sort(key=lambda u: u.full_name)

    selected_term_id = request.args.get("term_id")
    selected_program_id = request.args.get("program_id")

    grouped_courses = {}
    for c in courses:
        prog = c.program
        prog_name = prog.name if prog else "รายวิชาทั่วไป"
        prog_id = c.program_id if c.program_id else "0"
        grouped_courses.setdefault(prog_id, {"name": prog_name, "courses": []})
        grouped_courses[prog_id]["courses"].append(c)

    return render_template(
        "academic/open_course.html",
        grouped_courses=grouped_courses,
        terms=terms,
        instructors=instructors,
        selected_term_id=selected_term_id,
        selected_program_id=selected_program_id,
    )


@app.route("/academic/assign-instructor/<section_id>", methods=["POST"])
@login_required
@roles_required("head")
def assign_instructor(section_id):
    section = _get_or_404(Section, section_id)

    # Head can only assign instructors within their own department/program scope
    program_ids = set()
    if current_user.department_id:
        program_ids = {p.id for p in Program.find_by("department_id", current_user.department_id) if p.id}
    elif current_user.program_id:
        program_ids = {current_user.program_id}

    course = Course.get(section.course_id)
    if not course or not course.program_id or (course.program_id not in program_ids):
        flash("คุณไม่มีสิทธิ์มอบหมายผู้สอนให้รายวิชานี้", "danger")
        return _safe_redirect_next("head_dashboard")

    instructor_id_raw = (request.form.get("instructor_id") or "").strip()
    if not instructor_id_raw:
        section.instructor_id = None
        section.save()
        flash("ยกเลิกการมอบหมายผู้สอนแล้ว", "info")
        return _safe_redirect_next("head_dashboard")

    instructor = User.get(instructor_id_raw)
    if (not instructor) or (not instructor.has_role("instructor")):
        flash("ไม่พบข้อมูลอาจารย์ผู้สอน", "danger")
        return _safe_redirect_next("head_dashboard")

    if current_user.department_id:
        allowed = (instructor.department_id == current_user.department_id) or (instructor.program_id in program_ids)
    else:
        allowed = instructor.program_id in program_ids

    if not allowed:
        flash("ไม่สามารถมอบหมายผู้สอนข้ามสาขา/หลักสูตรได้", "danger")
        return _safe_redirect_next("head_dashboard")

    section.instructor_id = instructor_id_raw
    section.save()
    flash("มอบหมายผู้สอนเรียบร้อย", "success")
    return _safe_redirect_next("head_dashboard")


@app.route("/academic/toggle-open-tqf3/<section_id>", methods=["POST"])
@login_required
@roles_required("academic")
def toggle_open_tqf3(section_id):
    section = _get_or_404(Section, section_id)

    if get_active_role() != "academic":
        flash("โปรดสลับบทบาทเป็นฝ่ายวิชาการเพื่อดำเนินการ", "warning")
        return redirect(url_for("dashboard"))

    if _is_system_locked():
        flash("ระบบถูกล็อกอยู่ ไม่สามารถเปิด/ปิดให้กรอกได้", "warning")
        return _safe_redirect_next("academic_dashboard")

    # Deprecated: opening is now term-wide. Keep this endpoint to avoid breaking old links.
    term = _get_or_404(Term, section.term_id)
    term.is_open_tqf3 = not bool(term.is_open_tqf3)
    term.save()
    flash(
        f"สถานะการเปิดกรอก มคอ.3 (ทั้งเทอม {term.semester}/{term.year}): "
        f"{'เปิดให้เริ่มกรอก' if term.is_open_tqf3 else 'ปิดห้ามกรอก'}",
        "info",
    )
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/toggle-open-tqf5/<section_id>", methods=["POST"])
@login_required
@roles_required("academic")
def toggle_open_tqf5(section_id):
    section = _get_or_404(Section, section_id)

    if get_active_role() != "academic":
        flash("โปรดสลับบทบาทเป็นฝ่ายวิชาการเพื่อดำเนินการ", "warning")
        return redirect(url_for("dashboard"))

    if _is_system_locked():
        flash("ระบบถูกล็อกอยู่ ไม่สามารถเปิด/ปิดให้กรอกได้", "warning")
        return _safe_redirect_next("academic_dashboard")

    # Deprecated: opening is now term-wide. Keep this endpoint to avoid breaking old links.
    term = _get_or_404(Term, section.term_id)
    term.is_open_tqf5 = not bool(term.is_open_tqf5)
    term.save()
    flash(
        f"สถานะการเปิดกรอก มคอ.5 (ทั้งเทอม {term.semester}/{term.year}): "
        f"{'เปิดให้เริ่มกรอก' if term.is_open_tqf5 else 'ปิดห้ามกรอก'}",
        "info",
    )
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/term/<term_id>/toggle-open-tqf3", methods=["POST"])
@login_required
@roles_required("academic")
def toggle_open_term_tqf3(term_id):
    term = _get_or_404(Term, term_id)

    if get_active_role() != "academic":
        flash("โปรดสลับบทบาทเป็นฝ่ายวิชาการเพื่อดำเนินการ", "warning")
        return redirect(url_for("dashboard"))

    if _is_system_locked():
        flash("ระบบถูกล็อกอยู่ ไม่สามารถเปิด/ปิดให้กรอกได้", "warning")
        return _safe_redirect_next("academic_dashboard")

    term.is_open_tqf3 = not bool(term.is_open_tqf3)
    term.save()
    flash(
        f"สถานะการเปิดกรอก มคอ.3 (ทั้งเทอม {term.semester}/{term.year}): "
        f"{'เปิดให้เริ่มกรอก' if term.is_open_tqf3 else 'ปิดห้ามกรอก'}",
        "info",
    )
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/term/<term_id>/toggle-open-tqf5", methods=["POST"])
@login_required
@roles_required("academic")
def toggle_open_term_tqf5(term_id):
    term = _get_or_404(Term, term_id)

    if get_active_role() != "academic":
        flash("โปรดสลับบทบาทเป็นฝ่ายวิชาการเพื่อดำเนินการ", "warning")
        return redirect(url_for("dashboard"))

    if _is_system_locked():
        flash("ระบบถูกล็อกอยู่ ไม่สามารถเปิด/ปิดให้กรอกได้", "warning")
        return _safe_redirect_next("academic_dashboard")

    term.is_open_tqf5 = not bool(term.is_open_tqf5)
    term.save()
    flash(
        f"สถานะการเปิดกรอก มคอ.5 (ทั้งเทอม {term.semester}/{term.year}): "
        f"{'เปิดให้เริ่มกรอก' if term.is_open_tqf5 else 'ปิดห้ามกรอก'}",
        "info",
    )
    return _safe_redirect_next("academic_dashboard")


@app.route("/academic/delete-section/<section_id>", methods=["POST"])
@login_required
@roles_required("academic")
def delete_section(section_id):
    section = _get_or_404(Section, section_id)

    tqf3 = TQF3.first_by("section_id", section_id)
    tqf5 = TQF5.first_by("section_id", section_id)
    if tqf3 or tqf5:
        flash("ไม่สามารถลบได้ เนื่องจากมีการสร้างเอกสาร มคอ. แล้ว", "danger")
    else:
        section.delete()
        flash("ลบรายวิชาที่เปิดสอนเรียบร้อยแล้ว", "success")

    return _safe_redirect_next("academic_dashboard")


# --- CLI ---


@app.cli.command("seed-firestore")
def seed_firestore():
    """Create minimal initial users in Firestore for first login.

    This is intentionally explicit (no auto-seeding on startup).
    """
    defaults = [
        {
            "id": "admin",
            "username": "admin",
            "password": "password",
            "full_name": "System Administrator",
            "roles": ["admin"],
        },
        {
            "id": "academic",
            "username": "academic",
            "password": "password",
            "full_name": "Academic Officer",
            "roles": ["academic"],
        },
    ]

    created = 0
    for d in defaults:
        if User.get_by_username(d["username"]):
            continue
        u = User(
            id=d["id"],
            username=d["username"],
            password_hash=generate_password_hash(d["password"]),
            full_name=d["full_name"],
            roles=d["roles"],
        )
        u.save()
        created += 1

    print(f"Seeded users: {created} created")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the QualificationsFramework Flask app")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "5001")))
    debug_default = str(os.getenv("FLASK_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=debug_default,
        help="Enable/disable Flask debug mode (default from FLASK_DEBUG)",
    )
    parser.add_argument("--no-reload", action="store_true", help="Disable Werkzeug reloader")
    args = parser.parse_args()

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        use_reloader=(args.debug and not args.no_reload),
    )
