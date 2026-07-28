import copy
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def _tag_values(node: etree._Element) -> list[str]:
    return node.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS)


def _wrap_cell(cell: etree._Element, tag: str, alias: str) -> str:
    if tag in _tag_values(cell):
        return "existing"
    paragraphs = cell.xpath("./w:p", namespaces=NS)
    if not paragraphs:
        paragraph = etree.Element(W + "p")
        cell.append(paragraph)
        paragraphs = [paragraph]
    sdt = etree.Element(W + "sdt")
    properties = etree.SubElement(sdt, W + "sdtPr")
    tag_node = etree.SubElement(properties, W + "tag")
    tag_node.set(W + "val", tag)
    alias_node = etree.SubElement(properties, W + "alias")
    alias_node.set(W + "val", alias)
    showing = etree.SubElement(properties, W + "showingPlcHdr")
    del showing
    content = etree.SubElement(sdt, W + "sdtContent")
    for paragraph in paragraphs:
        cell.remove(paragraph)
        content.append(paragraph)
    tc_pr = cell.find(W + "tcPr")
    insert_at = 1 if tc_pr is not None else 0
    cell.insert(insert_at, sdt)
    return "created"


def _wrap_paragraph(paragraph: etree._Element, tag: str, alias: str) -> str:
    parent = paragraph.getparent()
    if parent.tag == W + "sdt" and tag in _tag_values(parent):
        return "existing"
    index = parent.index(paragraph)
    sdt = etree.Element(W + "sdt")
    properties = etree.SubElement(sdt, W + "sdtPr")
    tag_node = etree.SubElement(properties, W + "tag")
    tag_node.set(W + "val", tag)
    alias_node = etree.SubElement(properties, W + "alias")
    alias_node.set(W + "val", alias)
    content = etree.SubElement(sdt, W + "sdtContent")
    parent.remove(paragraph)
    content.append(paragraph)
    parent.insert(index, sdt)
    return "created"


def _table_number(table_no: str) -> int:
    match = re.fullmatch(r"T(\d+)", table_no)
    return int(match.group(1)) if match else 0


def _physical_table_number(table_no: str) -> int | None:
    """Map semantic mapping numbers to the template's top-level body tables."""
    number = _table_number(table_no)
    if 1 <= number <= 23:
        return number
    if number == 24 or number == 37:
        return None
    if 25 <= number <= 36:
        return number - 1
    if number == 38:
        return 36
    return None


def compile_template(source: Path, output: Path, mappings: list[dict[str, Any]],
                     table_rules: list[dict[str, Any]]) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"success": [], "warnings": [], "errors": [], "statistics": {}}
    table_rule_map = {item["tableNo"]: item for item in table_rules}
    with zipfile.ZipFile(source, "r") as archive:
        parts = {}
        for item in archive.infolist():
            normalized_name = item.filename.replace("\\", "/")
            normalized_info = copy.copy(item)
            normalized_info.filename = normalized_name
            parts[normalized_name] = (normalized_info, archive.read(item.filename))

    document_root = etree.fromstring(parts["word/document.xml"][1])
    all_tables = document_root.xpath("./w:body/w:tbl", namespaces=NS)
    body_paragraphs = document_root.xpath("./w:body/w:p", namespaces=NS)
    header_parts = sorted(name for name in parts if re.fullmatch(r"word/header\d+\.xml", name))
    header_roots = {name: etree.fromstring(parts[name][1]) for name in header_parts}
    original_stats = {
        "logicalTables": len(all_tables),
        "verticalMerges": len(document_root.xpath(".//w:vMerge", namespaces=NS)),
        "gridSpans": len(document_root.xpath(".//w:gridSpan", namespaces=NS)),
        "bookmarks": len(document_root.xpath(".//w:bookmarkStart", namespaces=NS)),
        "drawings": len(document_root.xpath(".//w:drawing", namespaces=NS)),
    }

    # Positions created interactively in ONLYOFFICE already exist in the draft
    # DOCX. In that case the stable content-control tag is the location; do not
    # wrap the paragraph/cell a second time or require a legacy XML locationId.
    existing_tags = set(document_root.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
    for root in header_roots.values():
        existing_tags.update(root.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))

    for mapping in mappings:
        if not mapping.get("enabled", True):
            continue
        location = mapping["locationId"]
        tag = mapping.get("controlTag", "")
        if mapping.get("fillRule") == "WORD_FIELD" or not tag:
            report["warnings"].append({"locationId": location, "code": "NO_CONTENT_CONTROL",
                                       "message": "Word域或空Tag保持原样"})
            continue
        if tag in existing_tags:
            report["success"].append({"locationId": location, "fieldCode": mapping["fieldCode"],
                                      "controlTag": tag, "action": "existing-content-control"})
            continue
        header_match = re.fullmatch(r"header\.table(\d+)\.row(\d+)\.cell(\d+)", location)
        body_match = re.fullmatch(r"body\.(T\d+)\.dataRow\.cell(\d+)", location)
        body_direct_match = re.fullmatch(r"body\.(T\d+)\.row(\d+)\.cell(\d+)", location)
        body_paragraph_match = re.fullmatch(r"body\.paragraph(\d+)", location)
        try:
            if header_match:
                if not header_parts:
                    raise IndexError("模板没有页眉 XML")
                header = header_roots[header_parts[0]]
                tables = header.xpath(".//w:tbl", namespaces=NS)
                table = tables[int(header_match.group(1)) - 1]
                row = table.xpath("./w:tr", namespaces=NS)[int(header_match.group(2)) - 1]
                cell = row.xpath("./w:tc", namespaces=NS)[int(header_match.group(3)) - 1]
                action = _wrap_cell(cell, tag, mapping["wordLabel"])
            elif body_match:
                table_no, cell_number = body_match.group(1), int(body_match.group(2))
                physical_number = _physical_table_number(table_no)
                if physical_number is None:
                    report["warnings"].append({"locationId": location, "code": "TABLE_NOT_IN_TEMPLATE",
                                               "message": f"{table_no} 在当前 Word 模板中没有独立表格"})
                    continue
                index = physical_number - 1
                if index < 0 or index >= len(all_tables):
                    raise IndexError(f"模板只有 {len(all_tables)} 张逻辑表格")
                rule = table_rule_map.get(table_no)
                if not rule or not rule.get("enabled", True):
                    report["warnings"].append({"locationId": location, "code": "TABLE_DISABLED",
                                               "message": f"{table_no} 未启用或没有布局规则"})
                    continue
                table = all_tables[index]
                rows = table.xpath("./w:tr", namespaces=NS)
                row_index = int(rule["dataRowStart"]) - 1
                if row_index < 0 or row_index >= len(rows):
                    raise IndexError(f"配置的数据行 {rule['dataRowStart']} 超出表格 {len(rows)} 行")
                cells = rows[row_index].xpath("./w:tc", namespaces=NS)
                if cell_number < 1 or cell_number > len(cells):
                    raise IndexError(f"数据行只有 {len(cells)} 个物理单元格")
                action = _wrap_cell(cells[cell_number - 1], tag, mapping["wordLabel"])
                bookmark_name = f"repeat_{table_no.lower()}_row"
                if not rows[row_index].xpath(f"./w:bookmarkStart[@w:name='{bookmark_name}']", namespaces=NS):
                    bookmark = etree.Element(W + "bookmarkStart")
                    bookmark.set(W + "id", str(2000 + index))
                    bookmark.set(W + "name", bookmark_name)
                    rows[row_index].insert(0, bookmark)
            elif body_direct_match:
                table_no = body_direct_match.group(1)
                physical_number = _physical_table_number(table_no)
                if physical_number is None:
                    report["warnings"].append({"locationId": location, "code": "TABLE_NOT_IN_TEMPLATE",
                                               "message": f"{table_no} 在当前 Word 模板中没有独立表格"})
                    continue
                index = physical_number - 1
                if index < 0 or index >= len(all_tables):
                    raise IndexError(f"模板只有 {len(all_tables)} 张逻辑表格")
                rows = all_tables[index].xpath("./w:tr", namespaces=NS)
                row_number, cell_number = int(body_direct_match.group(2)), int(body_direct_match.group(3))
                if row_number < 1 or row_number > len(rows):
                    raise IndexError(f"目标行 {row_number} 超出表格 {len(rows)} 行")
                cells = rows[row_number - 1].xpath("./w:tc", namespaces=NS)
                if cell_number < 1 or cell_number > len(cells):
                    raise IndexError(f"目标行只有 {len(cells)} 个物理单元格")
                action = _wrap_cell(cells[cell_number - 1], tag, mapping["wordLabel"])
            elif body_paragraph_match:
                paragraph_number = int(body_paragraph_match.group(1))
                if paragraph_number < 1 or paragraph_number > len(body_paragraphs):
                    raise IndexError(f"目标段落 {paragraph_number} 超出正文段落 {len(body_paragraphs)}")
                action = _wrap_paragraph(body_paragraphs[paragraph_number - 1], tag, mapping["wordLabel"])
            else:
                raise ValueError("无法识别 locationId 格式")
            report["success"].append({"locationId": location, "fieldCode": mapping["fieldCode"],
                                      "controlTag": tag, "action": action})
        except (IndexError, ValueError) as error:
            report["errors"].append({"locationId": location, "fieldCode": mapping.get("fieldCode"),
                                     "code": "LOCATION_INVALID", "message": str(error)})

    parts["word/document.xml"] = (parts["word/document.xml"][0], etree.tostring(
        document_root, xml_declaration=True, encoding="UTF-8", standalone=True
    ))
    for name, root in header_roots.items():
        parts[name] = (parts[name][0], etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for _, (info, content) in parts.items():
            target.writestr(info, content)

    with zipfile.ZipFile(output, "r") as archive:
        compiled_root = etree.fromstring(archive.read("word/document.xml"))
        compiled_tags = []
        for name in ["word/document.xml", *header_parts]:
            compiled_tags += etree.fromstring(archive.read(name)).xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS)
    compiled_stats = {
        "logicalTables": len(compiled_root.xpath("./w:body/w:tbl", namespaces=NS)),
        "verticalMerges": len(compiled_root.xpath(".//w:vMerge", namespaces=NS)),
        "gridSpans": len(compiled_root.xpath(".//w:gridSpan", namespaces=NS)),
        "bookmarks": len(compiled_root.xpath(".//w:bookmarkStart", namespaces=NS)),
        "drawings": len(compiled_root.xpath(".//w:drawing", namespaces=NS)),
        "contentControls": len(compiled_tags),
        "uniqueTags": len(set(compiled_tags)),
    }
    for key in ("logicalTables", "verticalMerges", "gridSpans", "drawings"):
        if compiled_stats[key] != original_stats[key]:
            report["errors"].append({"code": "STRUCTURE_CHANGED", "message": f"{key} 从 {original_stats[key]} 变为 {compiled_stats[key]}"})
    report["statistics"] = {"original": original_stats, "compiled": compiled_stats,
                            "mapped": len(report["success"]), "warnings": len(report["warnings"]),
                            "errors": len(report["errors"]), "tagDuplicates": {
                                tag: count for tag, count in Counter(compiled_tags).items() if count > 1
                            }}
    report["valid"] = not report["errors"]
    return report
