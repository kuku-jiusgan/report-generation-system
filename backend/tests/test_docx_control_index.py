"""字段的绑定状态必须以模板文档为准，不能只看映射里拼出来的 locationId。"""

import tempfile
import zipfile
from pathlib import Path

from lxml import etree

from backend.app.services.docx_control_index import control_locations, describe_binding


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
