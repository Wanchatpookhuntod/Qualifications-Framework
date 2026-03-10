# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run dev server (port 5001)
python app.py
# or
flask --app app run --host 0.0.0.0 --port 5001

# Seed baseline data (faculties/programs/users: admin/password, academic/password)
python -m flask --app app seed-firestore

# Seed richer demo data
python seed_data.py
python seed_multimedia.py  # multimedia curriculum from multimedia_curriculum.json
python verify_seed.py      # sanity-check seeded data

# Database utilities
python clean_db.py                                    # wipe major collections + create minimal users
python check_program.py                               # inspect program → courses/users/sections
python purge_curriculum_uploads.py --limit 5          # dry-run
python purge_curriculum_uploads.py --all --yes        # delete all curriculum_uploads

# Lint / format (install separately if needed)
ruff check . && ruff format --check .
black --line-length 100 .

# Tests (no suite yet; commands for when tests are added)
pytest -q
pytest tests/test_models.py::TestClass::test_method -vv
pytest -k "tqf5"
```

## Architecture

### Entry point & routing
`app.py` (~3600 lines) contains the entire Flask app: all routes, access-control decorators, CSV/JSON bulk-import parsers, and the `seed-firestore` CLI command. There is no blueprint split. Role-based access is enforced manually inside each view using `current_user.best_role()` and the `ROLE_PRIORITY` list `["admin", "academic", "head", "instructor"]`.

### Data layer
`models.py` — all Firestore models as Python dataclasses extending `FirestoreModel`. Key patterns:
- `FirestoreModel.save()` handles both create (new doc id) and update (merge), auto-setting timestamps.
- `find_by(field, value)`, `first_by(field, value)`, `find_all()` are the standard query helpers.
- `find_in(field, values)` chunks Firestore `in` queries into batches of ≤10 (Firestore limit).
- Related documents are fetched via lazy `@property` accessors (e.g. `section.course`, `program.faculty`).
- Runtime caches (`_course_cache`, `_term_cache`) on `Section` are not persisted to Firestore.

`firestore_db.py` — singleton Firestore client. Credential resolution order: `GOOGLE_APPLICATION_CREDENTIALS` env var → Application Default Credentials → `instance/qualificationsframework-34219c0bd960.json`.

### Collection hierarchy
```
faculties
  └── departments (faculty_id)
        └── programs (department_id, faculty_id, year)
              └── courses (program_id)

terms
  └── term_programs (term_id, program_id)
        └── sections (term_id, course_id, program_id, instructor_id)
              ├── tqf3 (section_id)
              └── tqf5 (section_id)

users
feedback (tqf_type, tqf_id, reviewer_id)
head_tqf5_summaries (term_id, head_id)
curriculum_uploads
```

### Role workflow
1. **admin** creates users (with roles), faculties, programs, courses.
2. **academic** creates terms, opens sections (assigns course+program to a term), locks/unlocks TQF rounds (`is_open_tqf3`, `is_open_tqf5` on Term).
3. **head** assigns instructors to sections, toggles section-level open (`Section.is_open` for TQF3, `is_open_tqf5` for TQF5), reviews/approves TQF3 and TQF5 documents.
4. **instructor** fills and submits TQF3 and TQF5 for their assigned sections.

### Templates
`templates/base.html` is the shared layout (glassmorphism theme, Inter + Sarabun fonts). All role-specific pages extend it and fill `{% block title %}` and `{% block content %}`. Role folders: `admin/`, `academic/`, `head/`, `instructor/`, `shared/`. Read-only TQF views are in `shared/tqf3_readonly.html` and `shared/tqf5_readonly.html`.

### Bulk course import
`_parse_courses_upload_text()` in `app.py` handles JSON, CSV, TSV, and pipe-delimited formats with Thai/English column header aliases (see `_COURSE_HEADER_MAP`). Reuse this parser; do not duplicate parsing logic.

## Key Conventions

- **No SQL**: Firestore only. Never introduce SQLAlchemy or other SQL dependencies.
- **No frontend build step**: vanilla HTML/CSS/JS only. Keep all styles in `static/css/style.css`.
- **Firestore client**: always use `firestore_db.get_firestore_client()`; never call `firebase_admin.initialize_app()` elsewhere.
- **Flash categories**: use `success`, `warning`, `danger`, `info` so `base.html` renders them correctly.
- **Thai strings**: UI copy should remain bilingual (Thai primary). Do not replace Thai strings with English-only.
- **FieldFilter**: use `FieldFilter` API for Firestore queries (already guarded with try/except for older SDK versions in `models.py`).
- **`instance/`**: treated as sensitive (credentials, runtime files). Never commit files from this directory.
- **Line length**: 100 characters; 4-space indent; no tabs.
- **Multi-role users**: `User.roles` is a list; `User.best_role()` returns the highest-priority role; `User.active_role` is set per-session.
