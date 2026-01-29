# QualificationsFramework (TQF System)

ระบบตัวอย่างสำหรับจัดการการเปิดรายวิชา/ภาคเรียน และการจัดทำเอกสาร **มคอ.3 (TQF3)** และ **มคอ.5 (TQF5)** ด้วย Flask + SQLite

## Tech Stack
- Python 3.10 (ดูไฟล์ `.python-version`)
- Flask, Flask-Login, Flask-SQLAlchemy
- SQLite (ไฟล์ DB: `tqf_system.db`)
- Jinja templates (โฟลเดอร์ `templates/`) + static assets (โฟลเดอร์ `static/`)

## โครงสร้างระบบ (Roles)
ระบบมีผู้ใช้หลัก 4 บทบาท:
- **admin**: จัดการคณะ/หลักสูตร/รายวิชา/ผู้ใช้
- **academic**: จัดการภาคเรียน, เปิดสอนรายวิชา (Section), lock/unlock รอบการกรอก
- **head**: ตรวจเอกสาร (approve/return), มอบหมายผู้สอน, toggle เปิดให้เริ่มกรอก (is_open)
- **instructor**: กรอก/ส่ง มคอ.3 และ มคอ.5

> Flow คร่าว ๆ อ้างอิงจาก `flow.md`: admin สร้าง user → (admin/academic) สร้างหลักสูตร/รายวิชา → academic สร้าง term/เปิดสอน → head/instructor จัดการเอกสาร

## Quick Start (Dev)
> แนะนำให้รันทุกคำสั่งจาก root ของโปรเจกต์ (โฟลเดอร์เดียวกับ `app.py`) เพื่อให้ path ของ SQLite ถูกต้อง

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
มี 2 วิธีหลัก:

**วิธี A: ใช้ Flask CLI (แนะนำสำหรับ reset+seed แบบครบชุด)**
```bash
flask --app app init-db
```
คำสั่งนี้จะ `drop_all()` + `create_all()` และ seed ข้อมูลจาก `seed_data.py`

**วิธี B: seed ด้วยสคริปต์โดยตรง**
```bash
python seed_data.py
```
สคริปต์จะ `create_all()` และ seed ข้อมูลตัวอย่าง

### 4) รันแอป
```bash
python app.py
```
แล้วเข้าใช้งานที่:
- http://localhost:5001

## Default Users (จาก seed_data.py)
เมื่อใช้ `seed_data.py` หรือ `flask --app app init-db` จะได้ผู้ใช้ตัวอย่าง:
- `admin` / `admin123` (role: admin)
- `academic1` / `academic123` (role: academic)
- `head1` / `head123` (role: head)
- `instructor1` / `pass123` (role: instructor)

> หมายเหตุ: `clean_db.py` จะสร้างผู้ใช้ `admin/password` และ `academic/password` แบบ minimal สำหรับกรณีล้างข้อมูล

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
- `clean_db.py`: ล้างข้อมูลตารางหลัก ๆ และสร้าง user ขั้นต่ำเพื่อ login ได้
- `check_program.py`: ตรวจความสัมพันธ์ program → courses/users/sections สำหรับ `Computer Science`

## Database Notes
- DB ใช้ SQLite และถูกตั้งค่าใน `app.py` เป็น:
  - `sqlite:///tqf_system.db`
- ไฟล์ DB จะถูกสร้างใน working directory ที่รันโปรแกรม (แนะนำให้รันจาก root โปรเจกต์เสมอ)

## โครงสร้างโฟลเดอร์สำคัญ
- `app.py`: Flask app + routes + CLI command `init-db`
- `models.py`: SQLAlchemy models (User, Course, Term, Section, TQF3, TQF5, Program, Faculty, Feedback)
- `templates/`: UI ตามบทบาท (admin/academic/head/instructor)
- `static/`: CSS/asset
- `instance/`: ไฟล์ runtime บางส่วน (เช่น text/data)

## Troubleshooting
- ถ้ารันแล้วหาแพ็กเกจไม่เจอ: ตรวจว่า activate venv แล้ว (`source .venv/bin/activate`)
- ถ้า login ไม่ได้หลังล้าง DB: รัน `flask --app app init-db` เพื่อ reset และ seed ใหม่
- ถ้า DB ไม่ถูกที่: ตรวจ working directory และดูว่ามีไฟล์ `tqf_system.db` อยู่ใน root โปรเจกต์หรือไม่
