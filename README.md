# QualificationsFramework (TQF System)

ระบบตัวอย่างสำหรับจัดการการเปิดรายวิชา/ภาคเรียน และการจัดทำเอกสาร **มคอ.3 (TQF3)** และ **มคอ.5 (TQF5)** ด้วย Flask + Firestore

## Tech Stack
- Python 3.10 (ดูไฟล์ `.python-version`)
- Flask, Flask-Login
- Firestore (Firebase Admin SDK)
- Jinja templates (โฟลเดอร์ `templates/`) + static assets (โฟลเดอร์ `static/`)

## โครงสร้างระบบ (Roles)
ระบบมีผู้ใช้หลัก 4 บทบาท:
- **admin**: จัดการคณะ/หลักสูตร/รายวิชา/ผู้ใช้
- **academic**: จัดการภาคเรียน, เปิดสอนรายวิชา (Section), lock/unlock รอบการกรอก
- **head**: ตรวจเอกสาร (approve/return), มอบหมายผู้สอน, toggle เปิดให้เริ่มกรอก (is_open)
- **instructor**: กรอก/ส่ง มคอ.3 และ มคอ.5

> Flow คร่าว ๆ อ้างอิงจาก `flow.md`: admin สร้าง user → (admin/academic) สร้างหลักสูตร/รายวิชา → academic สร้าง term/เปิดสอน → head/instructor จัดการเอกสาร

## Quick Start (Dev)
> แนะนำให้รันทุกคำสั่งจาก root ของโปรเจกต์ (โฟลเดอร์เดียวกับ `app.py`)

### 1) สร้าง virtualenv และติดตั้ง dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) ตั้งค่า Environment variables
โปรเจกต์ใช้ `python-dotenv` และเรียก `load_dotenv()` ใน `app.py`

สร้างไฟล์ `.env` (ถ้ายังไม่มี) เช่น:
```env
SECRET_KEY=change-me
PORT=5001
```
- `SECRET_KEY`: ใช้สำหรับ session/flash
- `PORT`: ค่า default ในโค้ดคือ `5001`

### 3) สร้าง DB และ seed ข้อมูลเริ่มต้น
ก่อน seed ให้เตรียม credential สำหรับ Firestore:
- ตั้งค่า `GOOGLE_APPLICATION_CREDENTIALS` ให้ชี้ไปที่ service account JSON หรือ
- ใช้ไฟล์ที่อยู่ใน `instance/qualificationsframework-34219c0bd960.json`

Seed ผู้ใช้ขั้นต่ำสำหรับ login:
```bash
python -m flask --app app seed-firestore
```

ถ้าต้องการ seed ข้อมูลตัวอย่างเพิ่ม (เช่น course/term/section + ผู้ใช้ตัวอย่าง):
```bash
python seed_data.py
```

### 4) รันแอป
```bash
python app.py
```
แล้วเข้าใช้งานที่:
- http://localhost:5001

## Default Users (จาก seed_data.py)
ค่าเริ่มต้นที่แนะนำ (จาก `seed-firestore`):
- `admin` / `password`
- `academic` / `password`

ถ้ารัน `seed_data.py` เพิ่ม จะได้ผู้ใช้ตัวอย่าง:
- `academic1` / `academic123`
- `head1` / `head123`
- `instructor1` / `pass123`

## การเพิ่มรายวิชาเข้า DB
- เพิ่มแบบ manual ได้ที่หน้า **Admin → Courses**
- สำหรับนำเข้าชุดหลักสูตร/รายวิชาเป็นจำนวนมาก ให้ใช้สคริปต์ seeding (ดูหัวข้อถัดไป)

## Seeding หลักสูตร Multimedia
มีสคริปต์ `seed_multimedia.py` ที่อ่าน `multimedia_curriculum.json` และ:
- สร้าง Faculty: `คณะวิทยาศาสตร์และเทคโนโลยี`
- สร้าง Program: `เทคโนโลยีมัลติมีเดีย` (ดึงปีจาก `revision_year`)
- เพิ่ม/อัปเดต Course พร้อม description (ถ้ามีใน JSON)

รัน:
```bash
python seed_multimedia.py
```
ตรวจสอบผลเร็ว ๆ:
```bash
python verify_seed.py
```

## Dev Utilities
- `clean_db.py`: ล้างข้อมูล collection หลัก ๆ และสร้าง user ขั้นต่ำเพื่อ login ได้
- `check_program.py`: ตรวจความสัมพันธ์ program → courses/users/sections สำหรับ `Computer Science`
- `purge_curriculum_uploads.py`: ลบข้อมูลเก่าใน collection `curriculum_uploads` (ค่าเริ่มต้นเป็น dry-run)

ตัวอย่าง:
```bash
# ดูจำนวนที่จะลบ (ไม่ลบจริง)
python purge_curriculum_uploads.py --limit 5

# ลบทั้งหมด (ลบจริง)
python purge_curriculum_uploads.py --all --yes

# ลบเฉพาะก่อนวันที่กำหนด
python purge_curriculum_uploads.py --before 2026-01-01 --yes
```

## Database Notes
- DB ใช้ Firestore ผ่าน Firebase Admin SDK
- ตั้งค่า credential ด้วย `GOOGLE_APPLICATION_CREDENTIALS` หรือใช้ไฟล์ใน `instance/`

## โครงสร้างโฟลเดอร์สำคัญ
- `app.py`: Flask app + routes + CLI command `seed-firestore`
- `models.py`: Firestore-backed models (User, Course, Term, Section, TQF3, TQF5, Program, Faculty, Feedback)
- `firestore_db.py`: Firestore client initializer
- `templates/`: UI ตามบทบาท (admin/academic/head/instructor)
- `static/`: CSS/asset
- `instance/`: ไฟล์ runtime บางส่วน (เช่น text/data)

## Troubleshooting
- ถ้ารันแล้วหาแพ็กเกจไม่เจอ: ตรวจว่า activate venv แล้ว (`source .venv/bin/activate`)
- ถ้า Firestore เชื่อมต่อไม่ได้: ตรวจ `GOOGLE_APPLICATION_CREDENTIALS` หรือไฟล์ใน `instance/` และสิทธิ์โปรเจกต์
