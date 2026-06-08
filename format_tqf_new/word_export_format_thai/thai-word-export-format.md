# Word Export Format สำหรับภาษาไทย

อ้างอิงฟอร์แมตจากไฟล์ต้นฉบับ:

`/Users/studiomac/Downloads/10042569 ปรับปรุง มคอ 3 เกณฑ์ 65.docx`

ไฟล์แม่แบบที่สร้าง:

`/Users/studiomac/Downloads/word_export_format_thai/10042569_export_template_thai_wordwrap.docx`

## หลักสำคัญ

Word จะตัดบรรทัดภาษาไทยได้ดีที่สุดเมื่อทำครบ 2 ชั้น:

1. ตั้งค่า DOCX ให้รู้ว่า run/paragraph เป็นภาษาไทย
2. ก่อน export ข้อความไทย ให้ตัดคำแล้วแทรก zero-width space (`U+200B`) ระหว่างคำ

ถ้าทำเฉพาะข้อ 1 บางเครื่องจะยังตัดกลางคำได้ โดยเฉพาะข้อความยาวในตารางหรือ cell แคบ ๆ

## DOCX Settings ที่ต้องมี

ใน `word/settings.xml`:

```xml
<w:characterSpacingControl w:val="doNotCompress"/>
<w:compat>
  <w:applyBreakingRules/>
</w:compat>
<w:themeFontLang w:val="th-TH" w:eastAsia="th-TH" w:bidi="th-TH"/>
```

ใน `word/styles.xml` และทุก run ที่สร้างใหม่:

```xml
<w:rPr>
  <w:rFonts
    w:ascii="Times New Roman"
    w:hAnsi="Times New Roman"
    w:eastAsia="Arial Unicode MS"
    w:cs="Arial Unicode MS"/>
  <w:lang w:val="th-TH" w:eastAsia="th-TH" w:bidi="th-TH"/>
  <w:sz w:val="24"/>
  <w:szCs w:val="24"/>
</w:rPr>
```

ใช้ font/size เดียวกับตำแหน่งเดิมของแบบฟอร์มได้ แต่ต้องมี `w:cs`, `w:szCs`, และ `w:lang` เสมอสำหรับข้อความไทย

## การจัดการขึ้นบรรทัดใหม่

แนะนำให้ normalize newline ก่อน export:

- `\r\n` และ `\r` เปลี่ยนเป็น `\n`
- `\n\n` ใช้แบ่งเป็น paragraph ใหม่
- `\n` เดี่ยว ใช้เป็น line break ใน paragraph เดิมด้วย `<w:br/>`

ตัวอย่าง OOXML:

```xml
<w:p>
  <w:r>
    <w:rPr>
      <w:lang w:val="th-TH" w:eastAsia="th-TH" w:bidi="th-TH"/>
    </w:rPr>
    <w:t xml:space="preserve">ข้อความบรรทัดแรก</w:t>
    <w:br/>
    <w:t xml:space="preserve">ข้อความบรรทัดสอง</w:t>
  </w:r>
</w:p>
```

## การตัดคำไทยก่อน export

ให้แทรก `U+200B` ระหว่างคำไทย เช่น:

```text
การจัดการเรียนการสอน
```

ควร export เป็น:

```text
การ​จัดการ​เรียน​การ​สอน
```

ตัวอักษร `U+200B` จะมองไม่เห็นใน Word แต่ช่วยให้ Word ตัดบรรทัดตรงขอบคำ

## กติกาสำหรับตาราง

- ห้ามใช้ fixed row height กับช่องที่มีข้อความไทยยาว
- ใช้ row height แบบ auto เพื่อให้ข้อความ wrap ได้
- กำหนด cell margin ซ้าย/ขวาอย่างน้อย 108 DXA ตามไฟล์ต้นฉบับ
- หลีกเลี่ยงการบังคับ `word-break: break-all` หรือการตัด string ด้วยจำนวนตัวอักษร
- ข้อความใน cell ต้องยังผ่านฟังก์ชันตัดคำและแทรก `U+200B`

## ถ้า export จาก HTML ไป Word

ใช้ CSS แนวนี้เป็นชั้นเสริม แต่ยังต้องแทรก `U+200B` ในข้อความจริง:

```html
<style>
  body, p, td, th {
    font-family: "Arial Unicode MS", "TH Sarabun New", "Cordia New", sans-serif;
    font-size: 12pt;
    mso-ansi-language: TH;
    mso-fareast-language: TH;
    mso-bidi-language: TH;
    word-break: keep-all;
    overflow-wrap: normal;
  }
  table {
    border-collapse: collapse;
    table-layout: fixed;
  }
  td, th {
    padding: 0 5.4pt;
    vertical-align: top;
  }
</style>
```

## Checklist ก่อนส่งออก

- ข้อความไทยผ่านตัวตัดคำและมี `U+200B`
- newline ถูกแปลงเป็น paragraph หรือ `<w:br/>` อย่างถูกชนิด
- run ที่เป็นภาษาไทยมี `w:lang` เป็น `th-TH`
- run ที่เป็นภาษาไทยมี font complex script (`w:cs`) และ size complex script (`w:szCs`)
- ตารางไม่มี fixed row height ที่ทำให้ข้อความโดนตัด
- ทดสอบด้วยข้อความไทยยาวใน cell แคบอย่างน้อย 1 จุด
