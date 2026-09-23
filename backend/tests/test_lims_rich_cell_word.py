"""Opt-in rich LIMS cell extraction and field-bound Word rendering."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from backend.app.services.lims_configured_extractor import apply_configured_extraction
from backend.app.services.lims_rule_schema import lims_rule_metadata, validate_lims_rule_config
from backend.app.services.mapped_docx_generator import build_mapped_docx
from backend.app.services.payload_paths import set_payload_path


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W_NS = NS["w"]
TABLE = """<table><tr><th>验证项目</th><th>溶液名称</th><th>配制方法</th></tr>
<tr><td rowspan="2">样品检测</td><td>第一种溶液</td><td>量取溶液。</td></tr>
<tr><td>第二种溶液</td><td><p>先配制母液：</p><table>
<tr><td rowspan="2">步骤</td><td colspan="2">用量</td></tr>
<tr><td>溶剂</td><td>10 ml</td></tr></table><p>混匀。</p></td></tr></table>"""


def _field() -> dict:
    return {"fieldCode": "method.preparation", "legacyJsonPath": "$.solutions[*].preparation",
            "cardinality": "ONE", "enabled": True, "dataType": "string"}


def _rule(format_name: str = "RICH_BLOCKS") -> dict:
    return {"fieldCode": "method.preparation", "enabled": True, "transform": "TRIM",
            "config": {"extractionType": "HTML_TABLE_COLUMN", "recordMode": "ROWS",
                       "sourcePath": "^配制方法$", "headerPattern": "验证项目.*配制方法",
                       "rowPattern": "验证项目=样品检测", "valueFormat": format_name}}


def _payload(format_name: str = "RICH_BLOCKS") -> dict:
    source = {"instanceId": "experiment-1", "richTexts": [{
        "id": "rich-1", "sectionPath": ["溶液配制"], "html": TABLE,
    }]}
    return apply_configured_extraction(source, {}, [_field()], [_rule(format_name)])


def _template(path: Path, *, inline: bool = False) -> None:
    control = ('<w:p><w:sdt><w:sdtPr><w:tag w:val="preparation"/></w:sdtPr>'
               '<w:sdtContent><w:r><w:t>模板文本</w:t></w:r></w:sdtContent></w:sdt></w:p>'
               if inline else '<w:tbl><w:tr><w:tc><w:sdt><w:sdtPr><w:tag w:val="preparation"/>'
               '</w:sdtPr><w:sdtContent><w:p><w:r><w:t>模板文本</w:t></w:r></w:p>'
               '</w:sdtContent></w:sdt></w:tc></w:tr></w:tbl>')
    xml = f'<w:document xmlns:w="{W_NS}"><w:body>{control}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


def _mapping() -> dict:
    return {"controlTag": "preparation", "fieldCode": "report.preparation",
            "standardFieldCode": "method.preparation", "sourcePath": "$.solutions[*].preparation",
            "sourceType": "LIMS", "enabled": True, "repeatType": "NONE"}


def test_rich_mode_preserves_mixed_cells_and_default_is_still_text() -> None:
    rows = _payload()["solutions"]
    assert rows[0]["preparation"] == {"type": "RICH_BLOCKS", "blocks": [
        {"type": "paragraph", "text": "量取溶液。"},
    ]}
    assert [block["type"] for block in rows[1]["preparation"]["blocks"]] == [
        "paragraph", "table", "paragraph",
    ]
    table = rows[1]["preparation"]["blocks"][1]
    assert table["rows"][0][0] == {"text": "步骤", "rowspan": 2, "colspan": 1}
    assert table["rows"][0][1] == {"text": "用量", "rowspan": 1, "colspan": 2}
    assert _payload("TEXT")["solutions"][0]["preparation"] == "量取溶液。"


def test_rich_mode_preserves_lims_subscript_in_extraction_and_word(tmp_path: Path) -> None:
    source = {"instanceId": "experiment-1", "richTexts": [{
        "id": "rich-1", "sectionPath": ["溶液配制"],
        "html": "<table><tr><th>验证项目</th><th>溶液名称</th><th>配制方法</th></tr>"
                "<tr><td>样品检测</td><td>C<sub>1</sub></td>"
                "<td>配制 C<sub>1</sub> 溶液。</td></tr></table>",
    }]}
    payload = apply_configured_extraction(source, {}, [_field()], [_rule()])
    preparation = payload["solutions"][0]["preparation"]
    assert preparation["blocks"][0]["text"] == "配制 C1 溶液。"
    assert preparation["blocks"][0]["runs"] == [
        {"text": "配制 C"},
        {"text": "1", "subscript": True},
        {"text": " 溶液。"},
    ]

    template, output = tmp_path / "template.docx", tmp_path / "report.docx"
    _template(template)
    build_mapped_docx(template, output, [_mapping()], payload,
                      {"source_payloads": {"LIMS": payload}, "field_sources": {
                          "method.preparation": {"type": "LIMS"},
                      }})
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    assert root.xpath('.//w:vertAlign/@w:val', namespaces=NS) == ["subscript"]


def test_rich_values_survive_standard_payload_path_write() -> None:
    extracted = _payload()["solutions"]
    resolved: dict = {}
    set_payload_path(resolved, "$.solutions[*].preparation",
                     [row["preparation"] for row in extracted])
    assert [row["preparation"] for row in resolved["solutions"]] == [
        row["preparation"] for row in extracted
    ]


def test_word_renders_each_method_with_a_native_nested_table(tmp_path: Path) -> None:
    template, output = tmp_path / "template.docx", tmp_path / "report.docx"
    _template(template)
    payload = _payload()
    build_mapped_docx(template, output, [_mapping()], payload,
                      {"source_payloads": {"LIMS": payload}, "field_sources": {
                          "method.preparation": {"type": "LIMS"},
                      }})
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    content = root.xpath('.//w:sdtContent', namespaces=NS)[0]
    assert [child.tag.rsplit('}', 1)[-1] for child in content] == ["p", "p", "tbl", "p"]
    assert content.xpath('./w:p//w:t/text()', namespaces=NS) == ["量取溶液。", "先配制母液：", "混匀。"]
    assert content.xpath('./w:tbl//w:t/text()', namespaces=NS) == ["步骤", "用量", "溶剂", "10 ml"]
    assert content.xpath('.//w:gridSpan/@w:val', namespaces=NS) == ["2"]
    assert content.xpath('.//w:vMerge/@w:val', namespaces=NS) == ["restart", "continue"]


def test_repeat_table_keeps_names_aligned_with_each_method(tmp_path: Path) -> None:
    template, output = tmp_path / "template.docx", tmp_path / "report.docx"
    control = lambda tag: (f'<w:sdt><w:sdtPr><w:tag w:val="{tag}"/></w:sdtPr>'
                           '<w:sdtContent><w:p><w:r><w:t>原型</w:t></w:r></w:p></w:sdtContent></w:sdt>')
    xml = (f'<w:document xmlns:w="{W_NS}"><w:body><w:tbl>'
           '<w:tr><w:tc><w:p><w:r><w:t>溶液名称</w:t></w:r></w:p></w:tc>'
           '<w:tc><w:p><w:r><w:t>配制方法</w:t></w:r></w:p></w:tc></w:tr>'
           f'<w:tr><w:tc>{control("name")}</w:tc><w:tc>{control("preparation")}</w:tc></w:tr>'
           '</w:tbl></w:body></w:document>')
    with zipfile.ZipFile(template, "w") as archive:
        archive.writestr("word/document.xml", xml)
    payload = _payload()
    for record, name in zip(payload["solutions"], ("第一种溶液", "第二种溶液")):
        record["name"] = name
    common = {"sourceType": "LIMS", "repeatType": "ROW", "tableNo": "GROUP:solutions",
              "groupItemPath": "$.solutions[*]", "enabled": True}
    mappings = [
        {**common, "controlTag": "name", "sourcePath": "$.solutions[*].name"},
        {**common, "controlTag": "preparation", "sourcePath": "$.solutions[*].preparation"},
    ]
    rules = [{"tableNo": "GROUP:solutions", "mode": "ROW_REPEAT", "physicalTableIndex": 1,
              "dataRowStart": 2}]
    build_mapped_docx(template, output, mappings, payload, {}, rules)
    with zipfile.ZipFile(output) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    rows = root.xpath('./w:body/w:tbl/w:tr', namespaces=NS)
    assert len(rows) == 3
    assert [row.xpath('./w:tc[1]//w:t/text()', namespaces=NS) for row in rows[1:]] == [
        ["第一种溶液"], ["第二种溶液"],
    ]
    assert not rows[1].xpath('./w:tc[2]//w:tbl', namespaces=NS)
    assert rows[2].xpath('./w:tc[2]//w:tbl', namespaces=NS)


def test_rich_mode_rejects_inline_word_control(tmp_path: Path) -> None:
    template, output = tmp_path / "template.docx", tmp_path / "report.docx"
    _template(template, inline=True)
    with pytest.raises(ValueError, match="块级内容控件"):
        build_mapped_docx(template, output, [_mapping()], _payload())


def test_rich_mode_rejects_incompatible_extraction_settings() -> None:
    definition = next(item for item in lims_rule_metadata()["extractionTypes"]
                      if item["value"] == "HTML_TABLE_COLUMN")
    options = next(field["options"] for group in definition["groups"] for field in group["fields"]
                   if field["key"] == "valueFormat")
    assert {option["value"] for option in options} == {"TEXT", "RICH_BLOCKS"}
    for setting in ({"recordMode": "MATRIX"}, {"valuePattern": ".*"}, {"valueTemplate": "{value}"}):
        with pytest.raises(ValueError, match="保留单元格段落和表格"):
            validate_lims_rule_config({**_rule()["config"], **setting}, "TRIM")
