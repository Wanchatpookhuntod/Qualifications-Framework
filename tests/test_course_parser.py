"""Smoke tests for the bulk course upload parser in app.py.

These exercise the pure parsing logic only — no Firestore access is required.
"""

from app import _normalize_header_key, _parse_courses_upload_text


def test_normalize_header_strips_and_lowercases():
    assert _normalize_header_key("  Code  ") == "code"
    assert _normalize_header_key("รหัส วิชา") == "รหัสวิชา"


def test_parse_json_list_with_thai_keys():
    text = """
    [
        {"รหัสวิชา": "MM101", "ชื่อวิชา": "หลักการมัลติมีเดีย", "หน่วยกิต": "3"},
        {"code": "MM102", "name_th": "ออกแบบกราฟิก", "name_en": "Graphic Design", "credits": 3}
    ]
    """
    result = _parse_courses_upload_text(text, "courses.json")

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["detected"]["type"] == "json"

    codes = [c["code"] for c in result["courses"]]
    assert codes == ["MM101", "MM102"]

    first = result["courses"][0]
    assert first["name_th"] == "หลักการมัลติมีเดีย"
    assert first["credits"] == "3"


def test_parse_csv_with_english_headers():
    text = "code,name_th,name_en,credits\nIT101,เทคโนโลยีสารสนเทศ,Intro to IT,3\n"
    result = _parse_courses_upload_text(text, "upload.csv")

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["detected"]["type"] == "csv"
    assert result["detected"]["delimiter"] == ","

    assert len(result["courses"]) == 1
    course = result["courses"][0]
    assert course["code"] == "IT101"
    assert course["name_th"] == "เทคโนโลยีสารสนเทศ"
    assert course["name_en"] == "Intro to IT"
    assert course["credits"] == "3"


def test_parse_empty_returns_error():
    result = _parse_courses_upload_text("", "empty.json")

    assert result["ok"] is False
    assert "ไฟล์ว่าง" in result["errors"][0]


def test_parse_json_missing_required_fields_reports_error():
    text = '[{"code": "X1"}]'  # missing name_th
    result = _parse_courses_upload_text(text, "bad.json")

    assert result["ok"] is False
    assert result["courses"] == []
    assert any("code และ name" in e for e in result["errors"])
