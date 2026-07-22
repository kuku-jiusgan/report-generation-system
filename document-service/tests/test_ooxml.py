from pathlib import Path
import zipfile
from app.ooxml_service import scan_controls, fill_controls

DOCUMENT='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:sdt><w:sdtPr><w:tag w:val="PROJECT_NAME"/><w:alias w:val="项目名称"/></w:sdtPr><w:sdtContent><w:r><w:t>{{PROJECT_NAME}}</w:t></w:r></w:sdtContent></w:sdt></w:p></w:body></w:document>'''
CONTENT='''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>'''

def fixture(path:Path):
    with zipfile.ZipFile(path,"w") as z:z.writestr("[Content_Types].xml",CONTENT);z.writestr("word/document.xml",DOCUMENT)

def test_scan_and_fill(tmp_path):
    src=tmp_path/"template.docx";out=tmp_path/"out.docx";fixture(src)
    assert scan_controls(src)["valid"] is True
    meta=fill_controls(src,out,{"PROJECT_NAME":"验证项目"},["PROJECT_NAME"])
    assert meta["filledTags"]==["PROJECT_NAME"]
    with zipfile.ZipFile(out) as z:assert "验证项目" in z.read("word/document.xml").decode()

