"""字段的绑定状态必须以模板文档为准，不能只看映射里拼出来的 locationId。"""

import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from lxml import etree

from backend.app.admin_routes.rule_catalog import _template_references
from backend.app.services.docx_control_index import control_locations, describe_binding
from backend.app.services.template_mapping_reconciliation import mappings_for_removed_controls


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _control(parent: etree._Element, tag: str, text: str) -> None:
    sdt = etree.SubElement(parent, W + "sdt")
    properties = etree.SubElement(sdt, W + "sdtPr")
    etree.SubElement(properties, W + "tag").set(W + "val", tag)
    content = etree.SubElement(sdt, W + "sdtContent")
    node = etree.SubElement(etree.SubElement(etree.SubElement(content, W + "p"), W + "r"), W + "t")
    node.text = text


def _template(path: Path) -> None:
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    etree.SubElement(etree.SubElement(body, W + "p"), W + "r")
    _control(body, "cc.overview", "概述")
    for _ in range(2):
        table = etree.SubElement(body, W + "tbl")
        for _ in range(2):
            row = etree.SubElement(table, W + "tr")
            for _ in range(3):
                etree.SubElement(row, W + "tc")
    second = body.xpath("./w:tbl", namespaces=NS)[1]
    _control(second.xpath("./w:tr", namespaces=NS)[1].xpath("./w:tc", namespaces=NS)[2], "cc.peakArea", "1593245")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True))


def test_control_locations_report_the_real_table_cell() -> None:
    with tempfile.TemporaryDirectory() as directory:
        template = Path(directory) / "template.docx"
        _template(template)

        locations = control_locations(template)

        assert locations["cc.peakArea"] == "正文第 2 张表 第 2 行第 3 格"
        assert locations["cc.overview"] == "正文第 2 段"


def test_binding_state_follows_the_document_not_the_mapping_row() -> None:
    with tempfile.TemporaryDirectory() as directory:
        template = Path(directory) / "template.docx"
        _template(template)
        locations = control_locations(template)

        bound = describe_binding(locations, "cc.peakArea")
        assert bound["bound"] and bound["wordLocation"] == "正文第 2 张表 第 2 行第 3 格"

        # 映射行还留着控件标签，但文档里已经没有这个控件了
        stale = describe_binding(locations, "cc.sequence")
        assert stale["bound"] is False
        assert stale["bindingState"] == "模板文档中找不到该控件"

        assert describe_binding(locations, "")["bindingState"] == "未设置内容控件"


def test_missing_template_file_does_not_claim_a_binding() -> None:
    assert control_locations(None) == {}
    assert control_locations(Path("/nonexistent/template.docx")) == {}
    assert describe_binding({}, "cc.peakArea")["bound"] is False


def test_rescan_after_the_template_changes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        template = Path(directory) / "template.docx"
        _template(template)
        assert "cc.peakArea" in control_locations(template)

        document = etree.Element(W + "document", nsmap={"w": W_NS})
        etree.SubElement(document, W + "body")
        with zipfile.ZipFile(template, "w") as archive:
            archive.writestr("word/document.xml", etree.tostring(document))
        # 缓存按修改时间失效：设计器里删掉控件后必须立刻反映出来
        import os
        os.utime(template, (0, 0))

        assert control_locations(template) == {}


def test_only_mappings_for_controls_removed_by_current_save_are_reconciled() -> None:
    mappings = [
        {"id": 1, "controlTag": "project.name"},
        {"id": 2, "controlTag": "legacy.pending"},
        {"id": 3, "controlTag": "still.present"},
        {"id": 4, "controlTag": ""},
    ]

    removed = mappings_for_removed_controls(
        mappings,
        previous_tags={"project.name", "still.present"},
        current_tags={"still.present", "new.control"},
    )

    assert [mapping["id"] for mapping in removed] == [1]


def test_template_references_only_include_controls_present_in_document(monkeypatch) -> None:
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = [{
        "template_name": "测试模板",
        "template_code": "TEST",
        "version_no": 1,
        "status": "DRAFT",
        "template_file": "/tmp/template.docx",
        "snapshot": """{"mappings": [
            {"fieldCode": "project.name", "standardFieldCode": "project.name", "controlTag": "present"},
            {"fieldCode": "project.name", "standardFieldCode": "project.name", "controlTag": "removed"}
        ]}""",
    }]
    repository = MagicMock()
    repository.database.connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(
        "backend.app.admin_routes.rule_catalog.control_locations",
        lambda _path: {"present": "正文第 1 段"},
    )

    references = _template_references(repository, "project.name")

    assert [reference["controlTag"] for reference in references] == ["present"]
    assert references[0]["bound"] is True
