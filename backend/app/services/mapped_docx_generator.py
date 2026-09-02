import copy
import logging
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .docx_field_values import (
    calculated_values, format_value, is_formula_calculation, set_control_text,
    source_mapping_value, tag_of,
)
from .docx_images import embed_image_controls
from .docx_language import normalize_part_languages, write_docx_parts_atomic
from .docx_repeat_rows import Warn, fill_repeat_rows
from .table_layout_rules import TableLayoutRules


logger = logging.getLogger(__name__)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W_NS, "r": R_NS}


def _warning_sink(report_data: dict[str, Any] | None) -> Warn:
    """把模板配置问题写进报告警告列表，用户在报告里能直接看到，同时留日志。"""
    warnings = report_data.setdefault("warnings", []) if isinstance(report_data, dict) else []

    def warn(code: str, table_no: str, message: str) -> None:
        text = f"模板配置警告 · {table_no}：{message}"
        if text not in warnings:
            warnings.append(text)
        logger.warning("模板配置警告 code=%s table=%s %s", code, table_no, message)

    return warn


def _fill_direct_controls(roots: dict[str, etree._Element], mappings: list[dict[str, Any]],
                          payload: dict[str, Any], report_data: dict[str, Any],
                          computed: dict[str, Any]) -> None:
    values: dict[str, str] = {}
    for mapping in mappings:
        tag = mapping.get("controlTag", "")
        if not tag or not mapping.get("enabled", True) or mapping.get("repeatType") == "ROW":
            continue
        value = (
            computed.get(str(mapping.get("fieldCode")))
            if is_formula_calculation(mapping)
            else source_mapping_value(mapping, payload, report_data)
        )
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if value is not None and not isinstance(value, (dict, list)):
            values[tag] = format_value(value, mapping)
    # 控件写回报告固定字段的对应关系来自映射规则的“报告字段绑定”，
    # 不再依赖后端常量表，设计器里改了就直接生效。
    for mapping in mappings:
        tag, binding = mapping.get("controlTag", ""), str(mapping.get("reportBindingCode") or "")
        if tag and binding and report_data.get(binding) not in (None, ""):
            values[tag] = str(report_data[binding])
    for root in roots.values():
        for control in root.xpath(".//w:sdt", namespaces=NS):
            tag = tag_of(control)
            if tag in values:
                set_control_text(control, values[tag])





def _clear_external_table_objects(document: etree._Element, layout: TableLayoutRules,
                                  warn: Warn) -> set[str]:
    """清空表内图片/嵌入对象；清哪几张表由表格规则的“清除表内图片”开关决定。"""
    relationship_ids: set[str] = set()
    tables = document.xpath("./w:body/w:tbl", namespaces=NS)
    for table_no in layout.object_clearing_tables():
        table_number = layout.physical_index(table_no)
        if table_number < 1 or table_number > len(tables):
            warn("CLEAR_OBJECT_TABLE_MISSING", table_no,
                 "勾选了清除表内图片，但没有配置有效的物理表格序号，本次跳过清理。")
            continue
        objects = tables[table_number - 1].xpath(
            ".//w:drawing | .//w:pict | .//w:object", namespaces=NS
        )
        for node in objects:
            relationship_ids.update(node.xpath(".//@r:id | .//@r:embed | .//@r:link", namespaces=NS))
            node.getparent().remove(node)
    return relationship_ids


def _remove_relationship_parts(parts: dict[str, tuple[Any, bytes]], relationship_ids: set[str]) -> None:
    if not relationship_ids:
        return
    rels_name = "word/_rels/document.xml.rels"
    if rels_name not in parts:
        return
    rels_root = etree.fromstring(parts[rels_name][1])
    removed_parts: set[str] = set()
    for relationship in list(rels_root):
        if relationship.get("Id") not in relationship_ids:
            continue
        if relationship.get("TargetMode") != "External":
            target = relationship.get("Target", "")
            removed_parts.add(posixpath.normpath(posixpath.join("word", target)))
        rels_root.remove(relationship)
    parts[rels_name] = (parts[rels_name][0], etree.tostring(
        rels_root, xml_declaration=True, encoding="UTF-8", standalone=True
    ))

    remaining_targets = {
        posixpath.normpath(posixpath.join("word", item.get("Target", "")))
        for item in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")
        if item.get("TargetMode") != "External"
    }
    orphaned_parts = removed_parts - remaining_targets
    for name in orphaned_parts:
        parts.pop(name, None)

    content_types_name = "[Content_Types].xml"
    if content_types_name in parts and orphaned_parts:
        content_types = etree.fromstring(parts[content_types_name][1])
        for override in list(content_types):
            if override.tag != f"{{{CONTENT_TYPES_NS}}}Override":
                continue
            if override.get("PartName", "").lstrip("/") in orphaned_parts:
                content_types.remove(override)
        parts[content_types_name] = (parts[content_types_name][0], etree.tostring(
            content_types, xml_declaration=True, encoding="UTF-8", standalone=True
        ))


def build_mapped_docx(compiled_template: Path, output: Path, mappings: list[dict[str, Any]],
                      payload: dict[str, Any] | None = None, report_data: dict[str, Any] | None = None,
                      table_rules: list[dict[str, Any]] | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(compiled_template, "r") as archive:
        parts = {}
        for item in archive.infolist():
            normalized_name = item.filename.replace("\\", "/")
            normalized_info = copy.copy(item)
            normalized_info.filename = normalized_name
            parts[normalized_name] = (normalized_info, archive.read(item.filename))

    normalize_part_languages(parts)

    xml_parts = [name for name in parts if name == "word/document.xml" or re.fullmatch(r"word/header\d+\.xml", name)]
    roots = {name: etree.fromstring(parts[name][1]) for name in xml_parts}
    active_mappings = [item for item in mappings if item.get("enabled", True)]
    # Keep the designer's original content when a newly created report has no
    # value for a mapped field. Direct fills replace controls that actually
    # have data; clearing every control here made a blank report erase its
    # template headings, names and example/default text before the editor
    # opened.
    layout = TableLayoutRules(table_rules)
    warn = _warning_sink(report_data)
    removed_relationship_ids = _clear_external_table_objects(roots["word/document.xml"], layout, warn)
    _remove_relationship_parts(parts, removed_relationship_ids)

    normalized_payload = payload or {}
    normalized_report = report_data or {}
    if normalized_payload or normalized_report:
        values = calculated_values(active_mappings, normalized_payload, normalized_report)
        _fill_direct_controls(roots, active_mappings, normalized_payload, normalized_report, values)
        fill_repeat_rows(
            roots["word/document.xml"], active_mappings, normalized_payload, normalized_report,
            values, layout, warn,
        )

    embed_image_controls(parts, roots, active_mappings)

    for name, root in roots.items():
        parts[name] = (parts[name][0], etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        ))
    write_docx_parts_atomic(parts, output)
