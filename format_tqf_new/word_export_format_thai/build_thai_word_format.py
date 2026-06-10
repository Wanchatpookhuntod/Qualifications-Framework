from pathlib import Path
import shutil
import zipfile
import xml.etree.ElementTree as ET


SOURCE_DOCX = Path("/Users/studiomac/Downloads/10042569 ปรับปรุง มคอ 3 เกณฑ์ 65.docx")
OUTPUT_DOCX = Path("/Users/studiomac/Downloads/word_export_format_thai/10042569_export_template_thai_wordwrap.docx")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"

ET.register_namespace("w", W_NS)
ET.register_namespace("w14", W14_NS)
ET.register_namespace("w15", W15_NS)
ET.register_namespace("mc", MC_NS)


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def attr(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def get_or_add(parent: ET.Element, tag: str, index: int | None = None) -> ET.Element:
    child = parent.find(w(tag))
    if child is None:
        child = ET.Element(w(tag))
        if index is None:
            parent.append(child)
        else:
            parent.insert(index, child)
    return child


def set_lang(element: ET.Element) -> None:
    element.set(attr("val"), "th-TH")
    element.set(attr("eastAsia"), "th-TH")
    element.set(attr("bidi"), "th-TH")


def ensure_run_language(root: ET.Element) -> None:
    for rpr in root.iter(w("rPr")):
        set_lang(get_or_add(rpr, "lang"))


def ensure_doc_defaults(root: ET.Element) -> None:
    doc_defaults = get_or_add(root, "docDefaults", 0)
    rpr_default = get_or_add(doc_defaults, "rPrDefault", 0)
    rpr = get_or_add(rpr_default, "rPr", 0)
    set_lang(get_or_add(rpr, "lang"))


def ensure_settings(root: ET.Element) -> None:
    character_spacing = root.find(w("characterSpacingControl"))
    if character_spacing is None:
        character_spacing = ET.Element(w("characterSpacingControl"))
        root.insert(0, character_spacing)
    character_spacing.set(attr("val"), "doNotCompress")

    compat = root.find(w("compat"))
    if compat is None:
        compat = ET.Element(w("compat"))
        root.append(compat)
    if compat.find(w("applyBreakingRules")) is None:
        compat.insert(0, ET.Element(w("applyBreakingRules")))

    theme_font_lang = root.find(w("themeFontLang"))
    if theme_font_lang is None:
        theme_font_lang = ET.Element(w("themeFontLang"))
        root.append(theme_font_lang)
    theme_font_lang.set(attr("val"), "th-TH")
    theme_font_lang.set(attr("eastAsia"), "th-TH")
    theme_font_lang.set(attr("bidi"), "th-TH")


def transform_xml(name: str, data: bytes) -> bytes:
    if not name.startswith("word/") or not name.endswith(".xml"):
        return data

    root = ET.fromstring(data)

    if name == "word/settings.xml":
        ensure_settings(root)

    if name == "word/styles.xml":
        ensure_doc_defaults(root)
        ensure_run_language(root)

    if name in {
        "word/document.xml",
        "word/footer1.xml",
        "word/header1.xml",
        "word/footnotes.xml",
        "word/endnotes.xml",
    }:
        ensure_run_language(root)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build() -> None:
    if not SOURCE_DOCX.exists():
        raise FileNotFoundError(SOURCE_DOCX)

    OUTPUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    tmp_docx = OUTPUT_DOCX.with_suffix(".tmp.docx")

    with zipfile.ZipFile(SOURCE_DOCX, "r") as zin, zipfile.ZipFile(tmp_docx, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            data = transform_xml(item.filename, data)
            zout.writestr(item, data)

    shutil.move(tmp_docx, OUTPUT_DOCX)
    print(OUTPUT_DOCX)


if __name__ == "__main__":
    build()
