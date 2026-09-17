"""缺失值必须执行字段空值规则，不能被模板占位文字掩盖。"""

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from backend.app.services.docx_field_values import format_value
from backend.app.services.mapped_docx_generator import build_mapped_docx


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
RULE = "PRESERVE_STYLE;EMPTY_AS_DASH"


@pytest.mark.parametrize("value, expected", [(None, "-"), ("", "-"), ([None], "-"), ("实际目的", "实际目的")])
@pytest.mark.parametrize("rule_key", ["fillRule", "standardFieldFillRule"])
def test_direct_field_applies_empty_rule(tmp_path: Path, value, expected: str, rule_key: str) -> None:
    template = tmp_path / "template.docx"
    output = tmp_path / "report.docx"
    xml = f'''<w:document xmlns:w="{W_NS}"><w:body>
      <w:p><w:r><w:t>目的</w:t></w:r></w:p>
      <w:sdt><w:sdtPr><w:tag w:val="purpose"/></w:sdtPr>
        <w:sdtContent><w:p><w:pPr><w:jc w:val="both"/></w:pPr>
          <w:r><w:rPr><w:b/></w:rPr><w:t>模板里的目的内容</w:t></w:r>
        </w:p></w:sdtContent>
      </w:sdt>
    </w:body></w:document>'''
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("word/document.xml", xml)
    mapping = {
        "controlTag": "purpose", "fieldCode": "purpose", "sourcePath": "$.purpose",
        "sourceType": "LIMS", "enabled": True, rule_key: RULE,
    }

    build_mapped_docx(template, output, [mapping], {"purpose": value})

    with zipfile.ZipFile(output) as archive:
        document = etree.fromstring(archive.read("word/document.xml"))
    assert document.xpath(".//w:sdt//w:t/text()", namespaces=NS) == [expected]
    assert document.xpath("./w:body/w:p//w:t/text()", namespaces=NS) == ["目的"]
    assert document.xpath(".//w:sdt//w:rPr/w:b", namespaces=NS)
    assert document.xpath(".//w:sdt//w:pPr/w:jc/@w:val", namespaces=NS) == ["both"]


def test_standard_suffix_rule_is_not_hidden_by_mapping_text_rule() -> None:
    mapping = {
        "fillRule": "TEXT",
        "standardFieldFillRule": "APPEND_SUFFIX:-线性与范围试验结果表",
    }

    assert format_value("测试1", mapping) == "测试1-线性与范围试验结果表"


def test_suffix_rule_can_be_combined_with_other_directives() -> None:
    mapping = {"fillRule": "PRESERVE_STYLE;EMPTY_AS_DASH;APPEND_SUFFIX:-结果表"}

    assert format_value("杂质A", mapping) == "杂质A-结果表"
    assert format_value("", mapping) == "-"
