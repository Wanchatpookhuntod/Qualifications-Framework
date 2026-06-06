"""Word (.docx) exporters for TQF3 (มคอ.3) and TQF5 (มคอ.5) documents.

These builders mirror the read-only layouts in
``templates/shared/tqf3_readonly.html`` and ``templates/shared/tqf5_readonly.html``
so the downloaded Word file matches what reviewers see on screen. Keep the field
keys and fallback order in sync with those templates.

The functions return an in-memory ``io.BytesIO`` ready to hand to Flask's
``send_file``. No Firestore access happens here; callers resolve the section /
course / term context and pass plain dictionaries in.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

# Font that ships with most Thai Office installs and renders Thai cleanly.
THAI_FONT = "TH Sarabun New"
_HEADING_COLOR = RGBColor(0x1F, 0x3A, 0x5F)
_MUTED_COLOR = RGBColor(0x55, 0x55, 0x55)
_DASH = "-"


def _apply_thai_font(run) -> None:
    """Force the Thai-capable font on every script class for a run."""
    run.font.name = THAI_FONT
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), THAI_FONT)


def _set_base_style(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = THAI_FONT
    style.font.size = Pt(14)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), THAI_FONT)


def _add_run(paragraph, text: str, *, bold: bool = False, size: int = 14,
             color: Optional[RGBColor] = None):
    run = paragraph.add_run("" if text is None else str(text))
    run.bold = bold
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    _apply_thai_font(run)
    return run


def _add_title(doc: Document, text: str, subtitle: str = "") -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(p, text, bold=True, size=20, color=_HEADING_COLOR)
    if subtitle:
        sp = doc.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(sp, subtitle, size=14, color=_MUTED_COLOR)


def _add_section_heading(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.space_before = Pt(8)
    _add_run(p, text, bold=True, size=16, color=_HEADING_COLOR)


def _add_field(doc: Document, label: str, value: Any) -> None:
    p = doc.add_paragraph()
    _add_run(p, f"{label}: ", bold=True)
    _add_run(p, _DASH if value in (None, "") else str(value))


def _add_paragraph_field(doc: Document, label: str, value: Any) -> None:
    lp = doc.add_paragraph()
    _add_run(lp, label, bold=True)
    bp = doc.add_paragraph()
    text = _DASH if value in (None, "") else str(value)
    _add_run(bp, text)


def _add_table(doc: Document, headers: List[str], rows: List[List[Any]]) -> None:
    if not rows:
        p = doc.add_paragraph()
        _add_run(p, "(ยังไม่มีข้อมูล)", color=_MUTED_COLOR)
        return
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, header in zip(table.rows[0].cells, headers):
        cell.paragraphs[0].clear()
        _add_run(cell.paragraphs[0], header, bold=True, size=13)
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.paragraphs[0].clear()
            text = _DASH if value in (None, "") else str(value)
            _add_run(cell.paragraphs[0], text, size=13)


def _g(data: Dict[str, Any], *keys: str, default: Any = _DASH) -> Any:
    """First non-empty value among ``keys`` (ctx fallbacks already merged in)."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _arr(data: Dict[str, Any], *keys: str) -> List[Any]:
    for key in keys:
        value = data.get(key)
        if value:
            return value
    return []


def _at(seq: List[Any], idx: int, default: Any = _DASH) -> Any:
    if idx < len(seq):
        value = seq[idx]
        return _DASH if value in (None, "") else value
    return default


def _max_indexed(data: Dict[str, Any], prefix: str,
                 exclude_prefix: Optional[str] = None) -> int:
    biggest = 0
    for key in data.keys():
        if not key.startswith(prefix):
            continue
        if exclude_prefix and key.startswith(exclude_prefix):
            continue
        suffix = key.rsplit("_", 1)[-1]
        if suffix.isdigit():
            biggest = max(biggest, int(suffix))
    return biggest


def _add_signatures(doc: Document, roles: List[str]) -> None:
    """Append static signature lines (name + date) for the given roles."""
    doc.add_paragraph()
    for role in roles:
        p = doc.add_paragraph()
        _add_run(p, f"ลงชื่อ {role} ", )
        _add_run(p, "......................................................")
        _add_run(p, "        วันที่ ........./........./.........")
        np = doc.add_paragraph()
        np.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(np, "(                                             )")


def _finalize(doc: Document) -> io.BytesIO:
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_tqf3_docx(general: Dict[str, Any], ctx: Dict[str, Any]) -> io.BytesIO:
    """Render a TQF3 (มคอ.3) Word document. ``general`` is ``tqf3.general_info``.

    ``ctx`` holds resolved fallbacks (faculty/program/course/term/instructor).
    """
    general = dict(general or {})
    doc = Document()
    _set_base_style(doc)

    course_code = _g(general, "course_code", default=ctx.get("course_code", _DASH))
    course_name = _g(general, "course_name", default=ctx.get("course_name", _DASH))
    _add_title(doc, "ประมวลการสอนและแผนการจัดการเรียนรู้ (มคอ.3)",
               "มหาวิทยาลัยราชภัฏเทพสตรี")
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(cp, f"{course_code} {course_name}".strip(), bold=True)

    # ข้อมูลรายวิชา (mirrors the official info table, in document order)
    _add_section_heading(doc, "ข้อมูลรายวิชา")
    _add_field(doc, "รหัสวิชา", course_code)
    _add_field(doc, "ชื่อวิชา", course_name)
    _add_field(doc, "จำนวนหน่วยกิต", _g(general, "credits", default=ctx.get("credits", _DASH)))
    _add_field(doc, "สถานภาพของวิชา", _g(general, "course_status"))
    _add_field(doc, "รายวิชาสังกัดคณะ", _g(general, "faculty", default=ctx.get("faculty", _DASH)))
    _add_field(doc, "หลักสูตร", _g(general, "program", default=ctx.get("program", _DASH)))
    _add_field(doc, "วิชาเอก", _g(general, "major"))
    _add_paragraph_field(doc, "คำอธิบายรายวิชา",
                         _g(general, "description", default=ctx.get("description", _DASH)))
    _add_field(doc, "รายวิชาที่บังคับเรียนก่อน (Pre-requisite) (ถ้ามี)", _g(general, "prereq"))
    _add_field(doc, "ภาคการศึกษา / ปีการศึกษา",
               f"{_g(general, 'semester', default=ctx.get('semester', _DASH))} / "
               f"{_g(general, 'academic_year', default=ctx.get('year', _DASH))}")
    _add_field(doc, "ประเภทนักศึกษา", _g(general, "student_type"))
    _add_field(doc, "ชั้นปีที่", _g(general, "year_level"))
    _add_field(doc, "อาจารย์ผู้สอน",
               _g(general, "instructor", default=ctx.get("instructor", _DASH)))
    _add_field(doc, "ห้องพัก", _g(general, "office"))
    _add_field(doc, "โทรศัพท์", _g(general, "phone"))
    _add_field(doc, "ห้องเรียน", _g(general, "location", "location_type"))
    _add_field(doc, "ระบบออนไลน์", _g(general, "online_system"))
    _add_field(doc, "กรณีเรียนภายนอกมหาวิทยาลัย", _g(general, "external_location"))
    _add_field(doc, "วันที่จัดทำหรือปรับปรุงประมวลการสอนหรือแผนการจัดการเรียนรู้ครั้งล่าสุด",
               _g(general, "last_updated"))
    _add_paragraph_field(doc, "ผลลัพธ์การเรียนรู้ ระดับหลักสูตร (PLOs) ที่เกี่ยวข้องกับรายวิชา",
                         _g(general, "plos"))
    _add_paragraph_field(doc, "จุดประสงค์การเรียนรู้ระดับรายวิชา (Course Learning Outcomes: CLOs)",
                         _g(general, "course_objective", "objectives"))
    hh = doc.add_paragraph()
    _add_run(hh, "จำนวนชั่วโมงที่ใช้ต่อสัปดาห์ในการจัดการเรียนรู้ (Hours/Week)", bold=True)
    _add_field(doc, "จำนวนชั่วโมงบรรยาย", _g(general, "lecture_hours"))
    _add_field(doc, "ชั่วโมงฝึกปฏิบัติ/ภาคสนาม/การฝึกงาน", _g(general, "lab_hours"))
    _add_field(doc, "ชั่วโมงการศึกษาด้วยตนเอง", _g(general, "self_hours"))
    _add_field(doc, "จำนวนชั่วโมงต่อสัปดาห์ที่จะให้คำปรึกษาและแนะนำทางวิชาการแก่นักศึกษา",
               _g(general, "consult_hours"))
    _add_paragraph_field(doc, "ช่องทางการติดต่ออาจารย์ผู้สอน", _g(general, "hours_note"))
    _add_paragraph_field(doc, "วิธีการ/ช่องทางสำหรับอุทธรณ์การเรียน",
                         _g(general, "appeal_channel"))

    # การพัฒนานักศึกษาตามผลลัพธ์การเรียนรู้ที่คาดหวัง (CLO table)
    _add_section_heading(doc, "การพัฒนานักศึกษาตามผลลัพธ์การเรียนรู้ที่คาดหวัง")
    clo_texts = _arr(general, "clo_text[]", "clo_desc[]")
    teachs = _arr(general, "teach_strategy[]")
    criterias = _arr(general, "assess_criteria[]")
    assesses = _arr(general, "assess_strategy[]")
    rows = [
        [_at(clo_texts, i), _at(teachs, i), _at(criterias, i), _at(assesses, i)]
        for i in range(len(clo_texts))
    ]
    _add_table(doc, ["ผลลัพธ์การเรียนรู้ที่คาดหวังของรายวิชา (CLOs)",
                     "กลยุทธ์การสอนตาม CLOs", "เกณฑ์การวัดและการประเมินผล",
                     "วิธีการวัดและประเมินผลตาม CLOs"], rows)
    n1 = doc.add_paragraph()
    _add_run(n1, "หมายเหตุ : ให้ระบุรายละเอียดของ CLOs, PLOs และกลยุทธ์การสอน "
             "วิธีการวัดประเมินผลที่สอดคล้องตามเล่มหลักสูตรกำหนด ในกรณีหลักสูตรใช้เกณฑ์มาตรฐาน 2558 "
             "ให้นำ TQF เดิมที่กำหนดในหลักสูตร (มคอ 2) มาใช้ไปพรางก่อน", size=13, color=_MUTED_COLOR)

    # แผนการจัดการเรียนรู้ (weekly plan; activity + media share one column per format)
    _add_section_heading(doc, "แผนการจัดการเรียนรู้")
    weeks = _arr(general, "week[]")
    topics = _arr(general, "topic[]", "plan_topic[]")
    week_clos = _arr(general, "week_clo[]", "plan_clo[]")
    hours = _arr(general, "hours[]")
    activities = _arr(general, "activities[]")
    medias = _arr(general, "media[]", "plan_media[]")
    teachers = _arr(general, "teacher[]")
    plan_lec = _arr(general, "plan_lecture[]")
    plan_prac = _arr(general, "plan_practice[]")
    plan_rows = []
    for i in range(len(topics)):
        wk = _at(weeks, i, default="")
        if str(wk).strip() == "":
            wk = i + 1
        hr = _at(hours, i, default="")
        if str(hr).strip() == "" and (plan_lec or plan_prac):
            try:
                total = float(_at(plan_lec, i, 0) or 0) + float(_at(plan_prac, i, 0) or 0)
            except (TypeError, ValueError):
                total = 0
            hr = total if total > 0 else _DASH
        act = _at(activities, i, default="")
        med = _at(medias, i, default="")
        act = "" if act in (None, _DASH) else str(act).strip()
        med = "" if med in (None, _DASH) else str(med).strip()
        if act and med:
            act_media = f"{act}\nสื่อที่ใช้: {med}"
        elif med:
            act_media = f"สื่อที่ใช้: {med}"
        else:
            act_media = act or _DASH
        plan_rows.append([
            wk, _at(topics, i), _at(week_clos, i),
            hr if str(hr).strip() else _DASH,
            act_media, _at(teachers, i),
        ])
    _add_table(doc, ["สัปดาห์ที่", "หัวข้อ / รายละเอียด", "Lesson Learning Outcome : LLOs",
                     "จำนวนชั่วโมง", "กิจกรรมการเรียนการสอน สื่อที่ใช้ (ถ้ามี)", "ผู้สอน"],
               plan_rows)

    # วิธีจัดการเรียนการสอน (ร้อยละของเวลา)
    _add_section_heading(doc, "วิธีจัดการเรียนการสอน")
    _add_field(doc, "การบรรยาย (ร้อยละของเวลาทั้งหมด)", _g(general, "pct_lecture"))
    _add_field(doc, "การบรรยายเชิงอภิปราย (ร้อยละ)", _g(general, "pct_discussion"))
    _add_field(doc, "กรณีศึกษา (ร้อยละ)", _g(general, "pct_case"))
    _add_field(doc, "การฝึกปฏิบัติ (ร้อยละ)", _g(general, "pct_practice"))
    _add_field(doc, "กิจกรรมกลุ่ม (ร้อยละ)", _g(general, "pct_group"))
    _add_field(doc, "อื่นๆ (ร้อยละ)", _g(general, "pct_other"))

    # แผนการประเมินตามผลลัพธ์การเรียนรู้ที่คาดหวังของรายวิชา
    _add_section_heading(doc, "แผนการประเมินตามผลลัพธ์การเรียนรู้ที่คาดหวังของรายวิชา")
    a_clo = _arr(general, "assess_clo[]")
    a_act = _arr(general, "assess_activity[]", "assess_method[]")
    a_crit = _arr(general, "assess_plan_criteria[]")
    a_pct = _arr(general, "assess_pct[]", "assess_ratio[]")
    assess_rows = [
        [_at(a_clo, i), _at(a_act, i), _at(a_crit, i), _at(a_pct, i)]
        for i in range(len(a_clo))
    ]
    _add_table(doc, ["ผลลัพธ์การเรียนรู้ที่คาดหวังของรายวิชา (CLOs)",
                     "กิจกรรมการจัดการเรียนรู้ของผู้เรียน",
                     "เกณฑ์การประเมินผลลัพธ์การเรียนรู้ระดับรายวิชา",
                     "สัดส่วนของการประเมินผล"], assess_rows)
    n2 = doc.add_paragraph()
    _add_run(n2, "หมายเหตุ กรณีหลักสูตรใช้เกณฑ์มาตรฐาน 2558 ให้ระบุ CLOs "
             "ตามที่ปรับในหมวดการพัฒนานักศึกษาตามผลลัพธ์การเรียนรู้ที่คาดหวัง",
             size=13, color=_MUTED_COLOR)

    # เครื่องมือสำคัญที่ใช้ประเมินผลลัพธ์การเรียนรู้ (Rubric Score)
    _add_section_heading(doc, "เครื่องมือสำคัญที่ใช้ประเมินผลลัพธ์การเรียนรู้ "
                         "(Rubric Score และเกณฑ์การตัดสินการบรรลุผลลัพธ์การเรียนรู้)")
    r_topic = _arr(general, "rubric_topic[]")
    r_l5 = _arr(general, "rubric_l5[]")
    r_l4 = _arr(general, "rubric_l4[]")
    r_l3 = _arr(general, "rubric_l3[]")
    r_l2 = _arr(general, "rubric_l2[]")
    r_l1 = _arr(general, "rubric_l1[]")
    rubric_rows = [
        [_at(r_topic, i), _at(r_l5, i), _at(r_l4, i), _at(r_l3, i), _at(r_l2, i), _at(r_l1, i)]
        for i in range(len(r_topic))
        if str(_at(r_topic, i, default="")).strip()
    ]
    _add_table(doc, ["ประเด็นการประเมิน", "ระดับ 5", "ระดับ 4",
                     "ระดับ 3", "ระดับ 2", "ระดับ 1"], rubric_rows)
    n3 = doc.add_paragraph()
    _add_run(n3, "ควรแนบ Rubric Score ที่ใช้ประเมินงานที่สะท้อน CLOs โดยประเด็นการประเมิน"
             "ควรวัดพฤติกรรมบ่งชี้ ความรู้ ทักษะ จริยธรรม หรือคุณลักษณะที่ต้องการวัดให้ชัดเจน "
             "และควรมีความสอดคล้องและสะท้อนการบรรลุ CLOs", size=13, color=_MUTED_COLOR)
    n4 = doc.add_paragraph()
    _add_run(n4, "หลักสูตรต้องกำหนด Rubric Score สำหรับใช้ประเมิน 1. ทักษะสื่อสาร "
             "2. ทักษะการทำงานร่วมกัน 3. ทักษะด้านเทคโนโลยีดิจิทัล "
             "4. ทักษะการคิดอย่างมีวิจารณญาณและการแก้ปัญหา 5. ความคิดสร้างสรรค์ "
             "6. จิตสำนึกสาธารณะ ซึ่งผู้สอนสามารถนำมาปรับประยุกต์ใช้ได้อย่างเหมาะสม",
             size=13, color=_MUTED_COLOR)

    # ตำราและเอกสารที่ใช้ประกอบการเรียนการสอน (APA)
    _add_section_heading(doc, "ตำราและเอกสารที่ใช้ประกอบการเรียนการสอน "
                         "(เขียนตามแบบบรรณานุกรม APA)")
    _add_paragraph_field(doc, "เอกสารอ้างอิง", _g(general, "references"))

    # การประเมินและปรับปรุงการจัดการเรียนรู้ของรายวิชา
    _add_section_heading(doc, "การประเมินและปรับปรุงการจัดการเรียนรู้ของรายวิชา")
    _add_paragraph_field(doc, "1. กลยุทธ์การประเมินการจัดการเรียนการสอนของรายวิชา",
                         _g(general, "course_eval_strategy"))
    _add_paragraph_field(doc, "2. การปรับปรุงการจัดการเรียนรู้ของรายวิชา",
                         _g(general, "course_improve", "improvement_strategy"))
    _add_paragraph_field(doc, "3. กระบวนการยืนยัน (verification) ผลสัมฤทธิ์ทางการเรียน "
                         "และผลลัพธ์การเรียนรู้ของนักศึกษา/ผู้เรียน",
                         _g(general, "verification"))

    _add_signatures(doc, ["อาจารย์ผู้สอน", "ประธานบริหารหลักสูตร"])

    return _finalize(doc)


def build_tqf4_docx(general: Dict[str, Any], ctx: Dict[str, Any]) -> io.BytesIO:
    """Render a TQF4 (มคอ.4) field-experience course spec. ``general`` is ``tqf4.general_info``."""
    general = dict(general or {})
    doc = Document()
    _set_base_style(doc)

    course_code = _g(general, "course_code", default=ctx.get("course_code", _DASH))
    course_name = _g(general, "course_name", default=ctx.get("course_name", _DASH))
    _add_title(doc, "ประมวลการสอนและแผนการจัดการเรียนรู้รายวิชาประสบการณ์ภาคสนาม (มคอ.4)",
               "มหาวิทยาลัยราชภัฏเทพสตรี")
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(cp, f"{course_code} {course_name}".strip(), bold=True)

    # 1) ข้อมูลรายวิชา
    _add_section_heading(doc, "1) ข้อมูลรายวิชา")
    _add_field(doc, "สถาบันการศึกษา", _g(general, "university",
               default="มหาวิทยาลัยราชภัฏเทพสตรี"))
    _add_field(doc, "คณะ", _g(general, "faculty", default=ctx.get("faculty", _DASH)))
    _add_field(doc, "หลักสูตร", _g(general, "program", default=ctx.get("program", _DASH)))
    _add_field(doc, "วิชาเอก", _g(general, "major"))
    _add_field(doc, "รหัสวิชา", course_code)
    _add_field(doc, "ชื่อวิชา", course_name)
    _add_field(doc, "สถานภาพของวิชา", _g(general, "course_status"))
    _add_field(doc, "หน่วยกิต", _g(general, "credits", default=ctx.get("credits", _DASH)))
    _add_field(doc, "ประเภทนักศึกษา", _g(general, "student_type"))
    _add_field(doc, "ชั้นปี", _g(general, "year_level"))
    _add_field(doc, "ภาคการศึกษา / ปีการศึกษา",
               f"{_g(general, 'semester', default=ctx.get('semester', _DASH))} / "
               f"{_g(general, 'academic_year', default=ctx.get('year', _DASH))}")
    _add_paragraph_field(doc, "คำอธิบายรายวิชา",
                         _g(general, "description", default=ctx.get("description", _DASH)))
    _add_field(doc, "รายวิชาที่เรียนก่อน", _g(general, "prereq"))
    _add_paragraph_field(doc, "เงื่อนไขที่สำคัญของการฝึกประสบการณ์", _g(general, "field_condition"))
    _add_field(doc, "อาจารย์ที่ปรึกษา/อาจารย์นิเทศ", _g(general, "advisor"))
    _add_field(doc, "ห้องพัก", _g(general, "office"))
    _add_field(doc, "โทรศัพท์", _g(general, "phone"))
    _add_field(doc, "ห้องเรียน/สถานที่", _g(general, "location", "location_type"))
    _add_field(doc, "ระบบออนไลน์", _g(general, "online_system"))
    _add_field(doc, "กรณีฝึกภายนอกมหาวิทยาลัย", _g(general, "external_location"))

    # 2) จุดประสงค์ + ภาระงาน
    _add_section_heading(doc, "2) จุดประสงค์การจัดการเรียนรู้ของการฝึกประสบการณ์ภาคสนาม")
    _add_paragraph_field(doc, "จุดประสงค์การจัดการเรียนรู้",
                         _g(general, "field_objective", "course_objective", "objectives"))
    _add_field(doc, "ชั่วโมงบรรยาย", _g(general, "lecture_hours"))
    _add_field(doc, "ชั่วโมงเตรียมความพร้อมของนักศึกษา", _g(general, "prep_hours"))
    _add_field(doc, "ชั่วโมงฝึกปฏิบัติ/ภาคสนาม/ฝึกงาน", _g(general, "practice_hours", "lab_hours"))
    _add_field(doc, "ชั่วโมงการศึกษาด้วยตนเอง", _g(general, "self_hours"))
    _add_field(doc, "ชั่วโมงที่อาจารย์นิเทศให้คำแนะนำ", _g(general, "advisor_consult_hours", "consult_hours"))
    _add_paragraph_field(doc, "ช่องทางสำหรับอุทธรณ์การเรียน", _g(general, "appeal_channel"))
    _add_paragraph_field(doc, "การจัดการเรียนรู้รายวิชาการฝึกประสบการณ์ภาคสนาม",
                         _g(general, "field_management"))

    # 3) รายงาน/งานที่มอบหมาย
    _add_section_heading(doc, "3) รายงานหรืองานที่นักศึกษาได้รับมอบหมายและกำหนดการส่งงาน")
    rep = _arr(general, "report[]")
    rep_crit = _arr(general, "report_criteria[]")
    rep_rows = [[_at(rep, i), _at(rep_crit, i)] for i in range(len(rep))]
    _add_table(doc, ["รายงาน/งานที่มอบหมาย/กำหนดส่งงาน", "เกณฑ์การวัดประเมินผลลัพธ์การเรียนรู้"],
               rep_rows)
    _add_paragraph_field(doc, "การติดตามผลการเรียนรู้การฝึกประสบการณ์ภาคสนาม",
                         _g(general, "follow_up"))
    _add_paragraph_field(doc, "หน้าที่และความรับผิดชอบของพี่เลี้ยงในสถานประกอบการ",
                         _g(general, "mentor_duties"))
    _add_paragraph_field(doc, "หน้าที่และความรับผิดชอบของอาจารย์ที่ปรึกษา/อาจารย์นิเทศ",
                         _g(general, "advisor_duties"))
    _add_paragraph_field(doc, "สิ่งอำนวยความสะดวกและการสนับสนุนที่ต้องการจากสถานประกอบการ",
                         _g(general, "facilities"))

    # 4) การวางแผนและเตรียมการ
    _add_section_heading(doc, "4) การวางแผนและการเตรียมการสำหรับการฝึกประสบการณ์ภาคสนาม")
    _add_paragraph_field(doc, "การกำหนดสถานที่ฝึกประสบการณ์ภาคสนาม", _g(general, "prep_location"))
    _add_paragraph_field(doc, "การเตรียมอาจารย์ที่ปรึกษา/อาจารย์นิเทศ", _g(general, "prep_advisor"))
    _add_paragraph_field(doc, "การเตรียมความพร้อมนักศึกษา", _g(general, "prep_student"))
    _add_paragraph_field(doc, "การเตรียมพี่เลี้ยงในสถานประกอบการ", _g(general, "prep_mentor"))
    _add_paragraph_field(doc, "การจัดการความเสี่ยง", _g(general, "risk_mgmt"))

    # 5) การพัฒนานักศึกษาตามผลลัพธ์การเรียนรู้
    _add_section_heading(doc, "5) การพัฒนานักศึกษาตามผลลัพธ์การเรียนรู้ที่คาดหวังของหลักสูตร")
    _add_paragraph_field(doc, "ผลลัพธ์การเรียนรู้ระดับหลักสูตร (PLOs) ที่เกี่ยวข้อง",
                         _g(general, "plos"))
    clo_texts = _arr(general, "clo_text[]", "clo_desc[]")
    clo_plo = _arr(general, "clo_plo[]", "plo[]")
    teachs = _arr(general, "teach_strategy[]")
    assesses = _arr(general, "assess_strategy[]")
    clo_rows = [
        [_at(clo_texts, i), _at(clo_plo, i), _at(teachs, i), _at(assesses, i)]
        for i in range(len(clo_texts))
    ]
    _add_table(doc, ["CLOs ฝึกประสบการณ์ภาคสนาม", "PLOs ที่รับผิดชอบ",
                     "กลยุทธ์การฝึกตาม CLOs", "วิธีการวัดและประเมินผลตาม CLOs"], clo_rows)

    # 6) แผนการฝึกรายสัปดาห์
    _add_section_heading(doc, "6) แผนการฝึกประสบการณ์ภาคสนาม")
    weeks = _arr(general, "week[]")
    topics = _arr(general, "topic[]")
    week_clos = _arr(general, "week_clo[]")
    hours = _arr(general, "hours[]")
    activities = _arr(general, "activities[]")
    supervisors = _arr(general, "supervisor[]")
    notes = _arr(general, "note[]")
    plan_rows = []
    for i in range(len(topics)):
        wk = _at(weeks, i, default="")
        if str(wk).strip() == "":
            wk = i + 1
        plan_rows.append([
            wk, _at(topics, i), _at(week_clos, i), _at(hours, i),
            _at(activities, i), _at(supervisors, i), _at(notes, i),
        ])
    _add_table(doc, ["สัปดาห์", "หัวข้อ/รายละเอียด", "CLOs", "ชั่วโมง",
                     "กิจกรรมการฝึกภาคสนาม", "ผู้ดูแลกิจกรรม", "หมายเหตุ"], plan_rows)

    # 7) แผนการประเมิน
    _add_section_heading(doc, "7) แผนการประเมินตามผลลัพธ์การเรียนรู้ของรายวิชาฝึกประสบการณ์ภาคสนาม")
    a_clo = _arr(general, "assess_clo[]")
    a_act = _arr(general, "assess_activity[]")
    a_crit = _arr(general, "assess_plan_criteria[]")
    a_pct = _arr(general, "assess_pct[]")
    a_eval = _arr(general, "assess_evaluator[]")
    assess_rows = [
        [_at(a_clo, i), _at(a_act, i), _at(a_crit, i), _at(a_pct, i), _at(a_eval, i)]
        for i in range(len(a_clo))
    ]
    _add_table(doc, ["CLOs", "กิจกรรมการประเมินผลการฝึก", "เกณฑ์การประเมิน",
                     "สัดส่วน (%)", "ผู้ประเมินผล"], assess_rows)

    # 8) Rubric Score
    _add_section_heading(doc, "8) เครื่องมือสำคัญที่ใช้ประเมินผลลัพธ์การเรียนรู้ (Rubric Score)")
    r_topic = _arr(general, "rubric_topic[]")
    r_l5 = _arr(general, "rubric_l5[]")
    r_l4 = _arr(general, "rubric_l4[]")
    r_l3 = _arr(general, "rubric_l3[]")
    r_l2 = _arr(general, "rubric_l2[]")
    r_l1 = _arr(general, "rubric_l1[]")
    rubric_rows = [
        [_at(r_topic, i), _at(r_l5, i), _at(r_l4, i), _at(r_l3, i), _at(r_l2, i), _at(r_l1, i)]
        for i in range(len(r_topic))
        if str(_at(r_topic, i, default="")).strip()
    ]
    _add_table(doc, ["ประเด็นการประเมิน", "ระดับ 5", "ระดับ 4",
                     "ระดับ 3", "ระดับ 2", "ระดับ 1"], rubric_rows)

    # 9) การประเมินและปรับปรุงจากผู้เกี่ยวข้อง
    _add_section_heading(doc, "9) การประเมินและปรับปรุงการจัดการเรียนรู้จากผู้ที่เกี่ยวข้อง")
    _add_paragraph_field(doc, "นักศึกษาที่ฝึกประสบการณ์ภาคสนาม", _g(general, "eval_student"))
    _add_paragraph_field(doc, "พี่เลี้ยงในสถานประกอบการ", _g(general, "eval_mentor"))
    _add_paragraph_field(doc, "อาจารย์ที่ปรึกษา/อาจารย์นิเทศ", _g(general, "eval_advisor"))
    _add_paragraph_field(doc, "อื่นๆ เช่น บัณฑิตจบใหม่", _g(general, "eval_other"))
    _add_paragraph_field(doc, "กระบวนการยืนยัน (verification) ผลการประเมินและการวางแผนปรับปรุง",
                         _g(general, "verification"))

    _add_signatures(doc, ["อาจารย์ผู้รับผิดชอบรายวิชา", "ประธานบริหารหลักสูตร"])

    return _finalize(doc)


def build_tqf5_docx(data: Dict[str, Any], ctx: Dict[str, Any]) -> io.BytesIO:
    """Render a TQF5 (มคอ.5) Word document. ``data`` is ``tqf5.actual_teaching``."""
    data = dict(data or {})
    doc = Document()
    _set_base_style(doc)

    course_code = _g(data, "course_code", default=ctx.get("course_code", _DASH))
    course_name = _g(data, "course_name", default=ctx.get("course_name", _DASH))
    _add_title(doc, "รายงานผลการจัดการเรียนรู้ระดับรายวิชาของหลักสูตร",
               "มหาวิทยาลัยราชภัฏเทพสตรี")
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(cp, f"{course_code} {course_name}".strip(), bold=True)

    # ข้อมูลรายวิชา (mirrors the official info table, in document order)
    _add_section_heading(doc, "ข้อมูลรายวิชา")
    _add_field(doc, "รหัสวิชา", course_code)
    _add_field(doc, "ชื่อวิชา", course_name)
    _add_field(doc, "จำนวนหน่วยกิต", _g(data, "credits", default=ctx.get("credits", _DASH)))
    _add_field(doc, "สถานภาพของวิชา", _g(data, "course_status"))
    _add_field(doc, "รายวิชาสังกัดคณะ", _g(data, "faculty", default=ctx.get("faculty", _DASH)))
    _add_field(doc, "หลักสูตร", _g(data, "program", default=ctx.get("program", _DASH)))
    _add_field(doc, "วิชาเอก", _g(data, "major"))
    _add_paragraph_field(doc, "คำอธิบายรายวิชา",
                         _g(data, "course_desc", default=ctx.get("description", _DASH)))
    _add_field(doc, "รายวิชาที่บังคับเรียนก่อน (Pre-requisite) (ถ้ามี)", _g(data, "prereq"))
    _add_paragraph_field(doc, "ผลลัพธ์การเรียนรู้ ระดับหลักสูตร (PLOs) ที่เกี่ยวข้องกับรายวิชา",
                         _g(data, "plos"))
    _add_paragraph_field(doc, "จุดประสงค์การจัดการเรียนรู้ ระดับรายวิชา "
                         "(รวมทั้งรายวิชาฝึกประสบการณ์ภาคสนาม)",
                         _g(data, "course_objective"))
    _add_field(doc, "ภาคการศึกษา / ปีการศึกษา",
               f"{_g(data, 'semester', default=ctx.get('semester', _DASH))} / "
               f"{_g(data, 'academic_year', default=ctx.get('year', _DASH))}")
    _add_field(doc, "ประเภทนักศึกษา", _g(data, "student_type"))
    _add_field(doc, "ชั้นปีที่", _g(data, "year_level"))
    _add_field(doc, "เงื่อนไขที่สำคัญของการฝึกประสบการณ์ (ถ้ามี)", _g(data, "field_condition"))
    _add_field(doc, "อาจารย์ผู้สอน",
               _g(data, "instructors", default=ctx.get("instructor", _DASH)))
    _add_paragraph_field(doc, "รายงานจำนวนชั่วโมงที่สอนจริงและที่คลาดเคลื่อนในการจัดการเรียนรู้ "
                         "(ถ้ามี) และแนวทางการจัดการแก้ไข",
                         _g(data, "teaching_hours"))
    _add_paragraph_field(doc, "รายงานหัวข้อที่สอนไม่ครอบคลุมจากแผนการจัดการเรียนรู้ที่กำหนดไว้ "
                         "(ถ้ามี) และแนวทางการจัดการแก้ไข",
                         _g(data, "uncovered_topics", "deviations"))
    _add_paragraph_field(doc, "รายงานความสอดคล้องกับจุดประสงค์การเรียนรู้ "
                         "และมีการปรับปรุงการจัดการเรียนรู้อย่างไร",
                         _g(data, "during_improve"))

    # การจัดการเรียนรู้และวิธีการประเมินผลที่ดำเนินการ (CLO table)
    _add_section_heading(doc, "การจัดการเรียนรู้และวิธีการประเมินผลที่ดำเนินการ"
                         "เพื่อทำให้เกิดผลลัพธ์การเรียนรู้ตามที่ระบุในรายละเอียดรายวิชา")
    legacy_codes = _arr(data, "clo_code[]")
    legacy_methods = _arr(data, "clo_method[]")
    legacy_assess = _arr(data, "clo_assess[]")
    legacy_results = _arr(data, "clo_result[]")
    clo_n = _max_indexed(data, "clo_desc_")
    if clo_n == 0 and legacy_codes:
        clo_n = len(legacy_codes)
    clo_rows = []
    for i in range(1, clo_n + 1):
        clo_rows.append([
            _g(data, f"clo_desc_{i}", default=_at(legacy_codes, i - 1)),
            _g(data, f"clo_plo_{i}"),
            _g(data, f"clo_teach_{i}", default=_at(legacy_methods, i - 1)),
            _g(data, f"clo_assess_{i}", default=_at(legacy_assess, i - 1)),
            _g(data, f"clo_result_{i}", default=_at(legacy_results, i - 1)),
            _g(data, f"clo_improve_{i}"),
        ])
    _add_table(doc, ["ผลลัพธ์การเรียนรู้ที่คาดหวังของรายวิชา (CLOs)",
                     "PLOs ที่รับผิดชอบ",
                     "กลยุทธ์การสอน/วิธีการจัดการเรียนรู้ที่ได้ดำเนินการ",
                     "วิธีการประเมินผลที่ได้ดำเนินการ/เกณฑ์การวัดและการประเมินผล",
                     "ผลที่เกิดกับนักศึกษา (บรรลุผลลัพธ์การเรียนรู้ระดับรายวิชา/ระดับหลักสูตร)",
                     "แนวทางการพัฒนาปรับปรุง เพื่อให้นักศึกษาบรรลุตามแต่ละ CLOs และ PLOs ที่รับผิดชอบ"],
               clo_rows)
    note = doc.add_paragraph()
    _add_run(note, "หมายเหตุ กรณีรายวิชาฝึกประสบการณ์วิชาชีพ "
             "ให้คำนึงถึงผลลัพธ์การเรียนรู้ที่กำหนดใน มคอ.2", size=13, color=_MUTED_COLOR)

    # สรุปผลการจัดการเรียนการสอนของรายวิชา (numbered items 1–10)
    _add_section_heading(doc, "สรุปผลการจัดการเรียนการสอนของรายวิชา")
    _add_field(doc, "1. จำนวนนักศึกษาที่ลงทะเบียน",
               _g(data, "n_registered", "students_enrolled"))
    _add_field(doc, "2. จำนวนนักศึกษาที่คงอยู่เมื่อสิ้นสุดภาคการศึกษา",
               _g(data, "n_remain", "students_finished"))
    _add_field(doc, "3. จำนวนนักศึกษาที่ถอน (W)",
               _g(data, "n_withdraw", "students_withdrawn"))

    g_head = doc.add_paragraph()
    _add_run(g_head, "4. การกระจายของระดับคะแนน (เกรด) (แสดงแยกตามสาขา) (ถ้ามี)", bold=True)
    grade_n = _max_indexed(data, "g_level_")
    grade_rows: List[List[Any]] = []
    if grade_n:
        for i in range(1, grade_n + 1):
            grade_rows.append([
                _g(data, f"g_level_{i}"),
                _g(data, f"g_count_{i}"),
                _g(data, f"g_percent_{i}"),
            ])
    else:
        for grade in ["A", "B+", "B", "C+", "C", "D+", "D", "F", "I", "S", "U", "W", "M"]:
            grade_rows.append([grade, data.get(f"grade_{grade}", 0), _DASH])
    _add_table(doc, ["ระดับคะแนน", "จำนวนนักศึกษา (คน)", "คิดเป็นร้อยละ"], grade_rows)

    a_head = doc.add_paragraph()
    _add_run(a_head, "5. การบรรลุผลลัพธ์การเรียนรู้ระดับรายวิชา "
             "และระดับหลักสูตรตาม PLOs ที่รับผิดชอบ", bold=True)
    _add_paragraph_field(doc, "5.1 การบรรลุผลลัพธ์การเรียนรู้ระดับรายวิชา (CLO) "
                         "เกณฑ์การวัดและการประเมินผลลัพธ์/ Rubric Score ที่กำหนด",
                         _g(data, "clo_achieve"))
    _add_paragraph_field(doc, "5.2 การบรรลุผลลัพธ์การเรียนรู้ระดับหลักสูตร (PLO ตัวที่รับผิดชอบ) "
                         "เกณฑ์การวัดและการประเมินผลลัพธ์/ Rubric Score ที่กำหนด",
                         _g(data, "plo_achieve"))
    _add_paragraph_field(doc, "6. ปัจจัยที่ทำให้นักศึกษาไม่บรรลุผลลัพธ์การเรียนรู้ "
                         "ระดับรายวิชา และระดับหลักสูตร",
                         _g(data, "fail_factors"))
    _add_paragraph_field(doc, "7. แนวทางการปรับปรุงแก้ไข กรณีที่นักศึกษาไม่บรรลุผลลัพธ์การเรียนรู้ "
                         "ระดับรายวิชา และระดับหลักสูตร",
                         _g(data, "fail_fix"))
    _add_paragraph_field(doc, "8. กระบวนการยืนยัน (verification) "
                         "ผลสัมฤทธิ์/ผลลัพธ์การเรียนรู้ของนักศึกษา",
                         _g(data, "verification", "verification_method"))

    i_head = doc.add_paragraph()
    _add_run(i_head, "9. ปัญหาและผลกระทบต่อการดำเนินการจัดการเรียนรู้", bold=True)
    issue_n = _max_indexed(data, "issue_", exclude_prefix="issue_fix_")
    issue_rows = [
        [_g(data, f"issue_{i}"), _g(data, f"issue_fix_{i}")]
        for i in range(1, issue_n + 1)
    ]
    _add_table(doc, ["ประเด็น", "แนวทางการปรับแก้ไข"], issue_rows)

    e_head = doc.add_paragraph()
    _add_run(e_head, "10. การประเมินผลรายวิชา", bold=True)
    _add_paragraph_field(doc, "1. ข้อวิพากษ์ที่สำคัญจากผลการประเมิน โดยนักศึกษาหรือผู้เรียน",
                         _g(data, "eval_crit"))
    _add_paragraph_field(doc, "2. ข้อคิดเห็นของผู้สอนต่อข้อวิพากษ์ตาม ข้อ 1",
                         _g(data, "teacher_comment"))
    _add_paragraph_field(doc, "3. แผนการปรับปรุงการจัดการเรียนรู้ของรายวิชา",
                         _g(data, "improve_plan", "improvement_plan"))
    _add_paragraph_field(doc, "4. ข้อเสนอแนะของผู้สอนต่อคณะกรรมการบริหารหลักสูตร",
                         _g(data, "suggest_to_committee"))

    _add_signatures(doc, ["อาจารย์ผู้สอน", "ประธานบริหารหลักสูตร"])

    return _finalize(doc)
