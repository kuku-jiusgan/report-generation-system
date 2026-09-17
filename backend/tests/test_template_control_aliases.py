import tempfile
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from backend.app.services.template_compiler import compile_template


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


def _template(path: Path) -> None:
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    control = etree.SubElement(body, W + "sdt")
    properties = etree.SubElement(control, W + "sdtPr")
    etree.SubElement(properties, W + "alias").set(W + "val", "检测限与定量限-结论")
    etree.SubElement(properties, W + "tag").set(W + "val", "cc.validation.conclusion")
    content = etree.SubElement(control, W + "sdtContent")
    text = etree.SubElement(etree.SubElement(etree.SubElement(content, W + "p"), W + "r"), W + "t")
    text.text = "正文保持不变"
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", etree.tostring(document))


def _repeat_template(path: Path) -> None:
    document = etree.Element(W + "document", nsmap={"w": W_NS})
    body = etree.SubElement(document, W + "body")
    table = etree.SubElement(body, W + "tbl")
    for row_number, tag in enumerate(("header", "detail", "conclusion"), start=1):
        row = etree.SubElement(table, W + "tr")
        if row_number == 3:
            bookmark = etree.SubElement(row, W + "bookmarkStart")
            bookmark.set(W + "id", "7")
            bookmark.set(W + "name", "repeat_group_results_row")
        cell = etree.SubElement(row, W + "tc")
        control = etree.SubElement(cell, W + "sdt")
        properties = etree.SubElement(control, W + "sdtPr")
        etree.SubElement(properties, W + "tag").set(W + "val", tag)
        etree.SubElement(control, W + "sdtContent")
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", etree.tostring(document))


def test_compiler_refreshes_existing_control_alias_without_rebuilding_content() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.docx"
        output = Path(directory) / "output.docx"
        _template(source)
        report = compile_template(source, output, [{
            "enabled": True, "locationId": "word.content_control.cc.validation.conclusion",
            "fieldCode": "report.validation.conclusion", "wordLabel": "检测限-结论",
            "controlTag": "cc.validation.conclusion", "repeatType": "NONE",
            "tableNo": "", "fillRule": "TEXT",
        }], [])

        assert report["valid"] is True
        assert report["success"][0]["action"] == "updated-content-control-alias"
        with ZipFile(output) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        assert root.xpath("string(.//w:sdtPr/w:alias/@w:val)", namespaces=NS) == "检测限-结论"
        assert root.xpath("string(.//w:sdtContent)", namespaces=NS) == "正文保持不变"


def test_compiler_moves_stale_repeat_bookmark_to_configured_data_row() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.docx"
        output = Path(directory) / "output.docx"
        _repeat_template(source)
        mappings = [{
            "enabled": True, "locationId": "word.content_control.conclusion",
            "fieldCode": "results.conclusion", "wordLabel": "结论",
            "controlTag": "conclusion", "repeatType": "ROW",
            "tableNo": "GROUP:results", "fillRule": "TEXT",
        }, {
            "enabled": True, "locationId": "word.content_control.detail",
            "fieldCode": "results.detail", "wordLabel": "明细",
            "controlTag": "detail", "repeatType": "ROW",
            "tableNo": "GROUP:results", "fillRule": "TEXT",
        }]
        rules = [{
            "tableNo": "GROUP:results", "mode": "TABLE_REPEAT", "enabled": True,
            "dataRowStart": 2, "physicalTableIndex": 1,
        }]

        report = compile_template(source, output, mappings, rules)

        assert report["valid"] is True
        with ZipFile(output) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        rows = root.xpath(".//w:tbl/w:tr", namespaces=NS)
        assert [
            row.xpath("./w:bookmarkStart/@w:name", namespaces=NS) for row in rows
        ] == [[], ["repeat_group_results_row"], []]
