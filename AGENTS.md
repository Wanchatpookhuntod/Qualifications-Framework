# AGENT OPERATIONS GUIDE
Shared reference for QualificationsFramework coding agents (Flask + Firestore).
Follow these conventions before making automated or manual commits.
Cursor/Copilot rules: none found (.cursor/ and .github have no policy files).
Treat everything under `instance/` (especially credentials) as sensitive and never commit secrets.

## Repository Snapshot
- Python 3.10 runtime; dependencies locked via `requirements.txt` (Flask, Flask-Login, firebase-admin, etc.).
- Application entrypoint is `app.py`; templates live under `templates/`, styles in `static/css/style.css`.
- Firestore models live in `models.py` using dataclasses plus helper accessors in `firestore_db.py`.
- CLI helper commands (e.g. seed-firestore) are wired through Flask's CLI in `app.py`.
- User roles: admin, academic, head, instructor; access control is manual inside views.
- Thai language strings are first-class; keep UI copy bilingual when feasible.
- No dedicated CI or test suite yet; manual QA plus scripted sanity checks are required.

## Environment Setup
1. `python3 -m venv .venv` then `source .venv/bin/activate` (always work inside the venv).
2. `python -m pip install -r requirements.txt` after every dependency change.
3. Create `.env` with `SECRET_KEY`, optional `PORT`, and any other per-dev values.
4. Point `GOOGLE_APPLICATION_CREDENTIALS` to a Firestore service account JSON or reuse `instance/qualificationsframework-34219c0bd960.json`.
5. When switching machines, delete `.venv` instead of mixing interpreters to avoid dependency drift.
6. Keep `cookies.txt`, `demo.txt`, and other ad-hoc files out of commits unless user-specified.
7. MacOS users: prefer `python3`/`pip3` shim to avoid system Python interference.

## Operational Commands
- Run dev server: `python app.py` (defaults to PORT env or 5001) for quick iteration.
- Alternative: `flask --app app run --host 0.0.0.0 --port 5001` when you need Flask CLI context.
- Initialize Firestore data: `python -m flask --app app seed-firestore` (creates baseline faculties/programs/users).
- Seed richer demo data: `python seed_data.py` and optionally `python seed_multimedia.py` then `python verify_seed.py`.
- Clean and reseed minimal data: `python clean_db.py` to wipe major collections.
- Inspect curriculum relationships: `python check_program.py --program "Computer Science"` (args optional).
- Purge uploads carefully: `python purge_curriculum_uploads.py --limit 5` (dry-run) or add `--all --yes` to delete.
- When editing static assets, run `python app.py` and manually refresh; there is no asset pipeline.

## Build / Lint / Test Commands
1. Install deps: `python -m pip install -r requirements.txt`.
2. Freeze new deps manually in `requirements.txt`; there is no poetry/pipenv.
3. Linting: project has no pinned tool, but run `python -m pip install ruff black` locally and execute `ruff check .` plus `ruff format --check .` before opening PRs.
4. Formatting: prefer `black --line-length 100 .` for Python files and Prettier (if installed) for HTML/CSS.
5. Static type sanity: optional `mypy app.py models.py` helps detect Firestore response mismatches.
6. Full test sweep (once tests exist): `pytest -q` from repo root.
7. Run a single test: `pytest tests/test_models.py::TestProgram::test_save -vv` (adapt file/class/method to your case).
8. Focused subset via keyword: `pytest -k "tqf5"`.
9. There is no JS build; lint JS snippets with `eslint` if you introduce significant scripts.
10. Always run `python app.py` after schema/model changes to ensure Firestore interactions still succeed.

## Data + Firestore Utilities
- Firestore client is a singleton from `firestore_db.get_firestore_client()`; never instantiate Firebase manually elsewhere.
- When testing without Firestore, stub `_firestore_client` or guard imports (`FieldFilter`) as done in `models.py`.
- Respect `ROLE_PRIORITY` ordering in `app.py` when computing `best_role()`.
- CSV/JSON upload parsers live inside `app.py` (`_parse_courses_upload_text`); reuse helpers instead of duplicating parsing logic.
- For mass updates, prefer programmatic calls to `.save()` on dataclasses; they automatically set timestamps.
- `TermProgram`, `Section`, `TQF3`, and `TQF5` objects embed runtime caches (`_course_cache` etc.); preserve these attributes when cloning instances.
- Delete operations should gracefully handle `None` ids: call `.delete()` only when `obj.id` exists.
- Always wrap Firestore writes that depend on request data with validation/normalization (strip strings, ensure ints).

## Manual QA Checklist
1. Login as each role (admin/academic/head/instructor) using seeded credentials and confirm nav items match role permissions.
2. Create a new Program and Course through the admin screens; ensure Firestore writes succeed.
3. Upload curriculum data (CSV/JSON) and verify `_parse_courses_upload_text` catches malformed rows.
4. Open/lock a Section from the academic dashboard and check toggles reflect in instructor view.
5. Submit TQF3/TQF5 drafts and ensure status badges update plus read-only versions render correctly.
6. Switch languages where available and confirm Thai strings still align with layout.
7. Smoke-test CLI helpers (`seed_multimedia.py`, `verify_seed.py`) after touching data model code.

## Code Style - General
- Target Python 3.10 features (pattern matching allowed, but keep readability first).
- Keep files ASCII unless UI copy requires Thai text (existing patterns already mix languages appropriately).
- Prefer early returns over deep nesting, as seen in `_parse_courses_upload_text` and `_import_courses_into_program`.
- Use descriptive helper names prefixed with `_` for view-only utilities to signal private scope.
- Document tricky logic with inline comments sparingly; most functions already self-document via naming.
- Keep functions under ~80 logical lines; split large blocks (e.g., CSV parsing) into helper functions when extending behavior.
- Maintain Thai transliterations already in place; do not replace user-facing strings with English-only variants.

## Code Style - Imports & Formatting
- Group imports: stdlib, third-party, local modules; separate each group with a blank line.
- Guard optional dependencies with `try/except ModuleNotFoundError` and provide actionable error messages (see Flask/dotenv guards).
- Prefer explicit imports over wildcard to keep linting simple.
- Stick to 4-space indentation; avoid tabs in Python and templates.
- Line length target is 100 characters; break long dict literals using parentheses and trailing commas.
- Constants (e.g., `ROLE_PRIORITY`) should be uppercase and defined near top-level context.
- When editing `requirements.txt`, keep entries sorted alphabetically.

## Code Style - Types & Naming
- Use `from __future__ import annotations` in modules that rely heavily on typing to avoid forward references.
- Dataclasses declare field defaults plus explicit types; use `Optional[str]` instead of raw `None` defaults.
- Naming: snake_case for functions/variables, PascalCase for dataclasses/classes, UPPER_SNAKE for constants.
- Keep helper sentinels (like `_RUNTIME_CACHE_NOT_SET`) module-private and descriptive.
- Use `typing.TypedDict` or `Protocol` if you add complex structures passed between helpers.
- When returning structured responses from helper functions, normalize to dicts like `{"ok": bool, "errors": list}` for consistency.

## Code Style - Flask Views & CLI
- Use `@login_required` for every route that touches user data; rely on `current_user.best_role()` for default role resolution.
- Flash messages should include category (`success`, `warning`, etc.) so `base.html` styling stays consistent.
- Validate request payloads (`request.form`, `request.files`) before hitting Firestore; guard against missing fields.
- When adding CLI commands, register them through Flask's CLI in `app.py` for consistency with existing `seed-firestore` command.
- Use `secure_filename` for uploads and store only sanitized filenames.
- Redirect users to role dashboards after POSTs to keep workflow discoverable.
- Keep JSON responses Thai-friendly where current UI expects Thai error text.

## Code Style - Firestore Models
- Extend `FirestoreModel` and implement `collection_name`, `to_dict`, and `from_dict` for every document type.
- Always sanitize/convert Firestore field types (e.g., convert `year` to `int`, booleans via `bool(...)`).
- Use `.save()` for creates and updates; it manages timestamps and id handling.
- Provide convenience properties (`program`, `course`, etc.) that fetch related documents lazily and cache when necessary.
- When adding queries, prefer `FieldFilter` compatibility as demonstrated in `find_by`.
- Keep Firestore interaction methods free of Flask context; they should be reusable from scripts/tests.

## Code Style - Templates & Static Assets
- Base layout is `templates/base.html`; extend it and fill `{% block title %}`, `{% block content %}`, and optional custom blocks.
- Use semantic HTML plus utility classes already defined in `static/css/style.css` (glass nav, cards, badges).
- Keep forms accessible: label inputs, include Thai copy, and use `.form-control` class names.
- When looping data, prefer `{% for row in rows %}` and guard with `{% if rows %}` to avoid empty placeholders.
- Inline scripts belong at the bottom of templates within `{% block scripts %}` and should avoid heavy dependencies.
- Keep fonts as defined (Inter + Sarabun) unless a brand change is required.
- Avoid introducing build-step CSS; keep styling inside existing CSS file and prefer custom properties.

## Error Handling & Messaging
- Input validators should return user-facing Thai messages (`"ไฟล์ว่าง"`, etc.) stored in the `errors` list.
- Wrap external API calls (Firebase, file IO) with `try/except` and bubble up actionable feedback in flashes.
- For CLI scripts, exit with non-zero status when operations fail; print summaries like counts of created/updated/skipped.
- Avoid swallowing exceptions silently; log or flash them depending on context.
- Use guard clauses for missing credentials and raise `FileNotFoundError` with clear setup instructions (see `firestore_db.py`).
- Mask sensitive values in logs; never print credential paths beyond necessity.

## Contribution Flow
1. Review `README.md` and this file before coding to keep workflows aligned.
2. Implement changes in focused commits; do not reformat untouched files.
3. If you add new dependencies or scripts, document them here and in `README.md`.
4. Run lint/test commands plus manual QA smoke checklist before requesting reviews.
5. Reference impacted roles/features inside PR descriptions (e.g., "head dashboard upload flow").
6. There is no default release automation; coordinate deploy steps manually with maintainers.
7. Keep AGENTS.md updated whenever workflows or style conventions change.

## Git & Workspace Hygiene
- You may be in a dirty git worktree; never revert user changes you did not make unless explicitly requested.
- When asked to make edits, stage only the files you touched and avoid formatting unrelated modules.
- Do not amend commits unless it was the one you created earlier in the session and the user explicitly asks.
- Never use destructive commands like `git reset --hard` or `git checkout --` without user approval.
- `instance/` contains credentials; ensure `.gitignore` keeps secrets from staging.
- Keep commit messages concise and focused on the intent (e.g., "fix head dashboard filters").

## Frontend Design Considerations
- Existing theme mixes glassmorphism with Inter/Sarabun typography; preserve that aesthetic unless a redesign is requested.
- Avoid generic layouts; use deliberate spacing, gradients, and animation hooks already present in `base.html` and `static/css/style.css`.
- Keep pages responsive; test nav drawer toggles on widths below 1024px when editing templates or CSS.
- Do not introduce heavy frontend frameworks or build steps; stick to vanilla HTML/CSS/JS.
- Honour bilingual requirements by pairing Thai + English labels where the UI already does so.
- Inline scripts should focus on progressive enhancement (e.g., pointer effects, nav toggle) and stay dependency-free.

## Performance & Security Notes
- Batch Firestore operations where practical to limit quota usage; reuse cached lookups instead of repeated `.get()` calls inside loops.
- Sanitize and strip all user input before saving; `secure_filename` is mandatory for uploads.
- Use session protection via Flask-Login and keep `SECRET_KEY` rotated across environments.
- Avoid loading large files into memory unless necessary; use streaming patterns for future bulk uploads.
- When exposing JSON endpoints, whitelist fields explicitly and never leak role metadata you do not need.
- Validate query parameters (year/semester) before using them in Firestore queries to prevent crashes.
