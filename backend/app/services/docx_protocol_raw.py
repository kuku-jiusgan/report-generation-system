"""按方案字段规则把段落或表格原始 Word 块复制到字段控件。"""

import copy
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .docx_language import W, W_NS
from .protocol_structure import read_protocol_structure

logger = logging.getLogger(__name__)
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W_NS, "r": R_NS}


def _direct_blocks(body: etree._Element) -> list[etree._Element]:
    return [item for item in body if item.tag in {W + "p", W + "tbl"}]


def _block_range(path: Path, config: dict[str, Any]) -> tuple[int, int]:
    blocks = read_protocol_structure(path)
    pattern = str(config.get("sectionPattern") or "").strip()
    if not pattern:
        raise ValueError("方案原文块必须配置起始章节或段落正则")
    try:
        matcher = re.compile(pattern)
    except re.error as error:
        raise ValueError(f"方案原文块起始正则无效：{error}") from error
    starts = [index for index, block in enumerate(blocks)
              if block["kind"] == "paragraph" and
              (matcher.fullmatch(block["section"]) if block["level"] is not None
               else matcher.search(block["text"]))]
    if len(starts) != 1:
        raise ValueError(f"方案原文块起始位置匹配到 {len(starts)} 处，请收紧起始正则")
    start = starts[0]
    heading = blocks[start]
    end_pattern = str(config.get("endPattern") or "").strip()
    if end_pattern:
        try:
            end_matcher = re.compile(end_pattern)
        except re.error as error:
            raise ValueError(f"方案原文块结束正则无效：{error}") from error
        ends = [index for index in range(start + 1, len(blocks))
                if blocks[index]["kind"] == "paragraph"
                and end_matcher.search(blocks[index]["text"])]
        if len(ends) != 1:
            raise ValueError(f"方案原文块结束位置匹配到 {len(ends)} 处，请收紧结束正则")
        end = ends[0]
    elif heading["level"] is not None:
        end = next((index for index in range(start + 1, len(blocks))
                    if blocks[index]["kind"] == "paragraph"
                    and blocks[index]["level"] is not None
                    and blocks[index]["level"] <= heading["level"]), len(blocks))
    else:
        raise ValueError("方案起始段落没有标题层级，请配置结束段落正则")
    if not config.get("includeStart", False):
        start += 1
    if start >= end:
        raise ValueError("方案原文块内容为空")
    return start, end


def _check_self_contained(blocks: list[etree._Element], label: str) -> None:
    if any(block.xpath(
        ".//@r:id | .//@r:embed | .//@r:link | .//w:numId | "
        ".//w:footnoteReference | .//w:endnoteReference | .//w:commentReference | "
        ".//w:sdt", namespaces=NS,
    ) for block in blocks):
        raise ValueError(f"方案原文块「{label}」包含图片、编号、引用或内容控件，暂不支持无损复制")


def _copy_blocks(blocks: list[etree._Element]) -> list[etree._Element]:
    copied = [copy.deepcopy(block) for block in blocks]
    for block in copied:
        # 书签只承载源文档内部导航，跨文档复制会造成名称和 ID 冲突；
        # 删除标记不改变可见文字、表格、公式或样式。
        for bookmark in block.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
            bookmark.getparent().remove(bookmark)
    return copied


def _source_style_closure(source_styles: etree._Element, style_ids: set[str]) -> dict[str, etree._Element]:
    definitions: dict[str, etree._Element] = {}
    pending = list(style_ids)
    while pending:
        style_id = pending.pop()
        if style_id in definitions:
            continue
        matches = source_styles.xpath("./w:style[@w:styleId=$style]", namespaces=NS, style=style_id)
        if len(matches) != 1:
            raise ValueError(f"方案原文块引用的样式 {style_id} 不存在或不唯一")
        definition = matches[0]
        if definition.xpath(".//w:numId", namespaces=NS):
            raise ValueError(f"方案原文块的样式 {style_id} 依赖编号定义，暂不支持无损复制")
        definitions[style_id] = definition
        pending.extend(value for value in definition.xpath(
            "./w:basedOn/@w:val | ./w:link/@w:val | ./w:next/@w:val", namespaces=NS,
        ) if value not in definitions)
    return definitions


def _copy_styles(blocks: list[etree._Element], source: zipfile.ZipFile,
                 parts: dict[str, tuple[Any, bytes]]) -> None:
    refs = [ref for block in blocks for ref in block.xpath(
        ".//w:tblStyle | .//w:pStyle | .//w:rStyle", namespaces=NS,
    )]
    if not refs:
        return
    name = "word/styles.xml"
    if name not in parts or name not in source.namelist():
        raise ValueError("方案原文块使用了样式，但方案或报告缺少 Word 样式定义")
    source_styles = etree.fromstring(source.read(name))
    target_styles = etree.fromstring(parts[name][1])
    existing = set(target_styles.xpath("./w:style/@w:styleId", namespaces=NS))
    originals = {str(ref.get(W + "val")) for ref in refs if ref.get(W + "val")}
    definitions = _source_style_closure(source_styles, originals)
    renamed = {style_id: "protocol_import_" + style_id for style_id in definitions}
    for original, definition in definitions.items():
        candidate = renamed[original]
        if candidate in existing:
            continue
        cloned = copy.deepcopy(definition)
        cloned.set(W + "styleId", candidate)
        cloned.attrib.pop(W + "default", None)
        for dependency in cloned.xpath("./w:basedOn | ./w:link | ./w:next", namespaces=NS):
            dependency.set(W + "val", renamed[str(dependency.get(W + "val"))])
        target_styles.append(cloned)
        existing.add(candidate)
    for ref in refs:
        ref.set(W + "val", renamed[str(ref.get(W + "val"))])
    parts[name] = (parts[name][0], etree.tostring(
        target_styles, xml_declaration=True, encoding="UTF-8", standalone=True,
    ))


def _target_control(document: etree._Element, tag: str) -> etree._Element:
    controls = document.xpath(".//w:sdt[w:sdtPr/w:tag/@w:val=$tag]", namespaces=NS, tag=tag)
    if len(controls) != 1:
        raise ValueError(f"方案原文块目标控件 {tag} 匹配到 {len(controls)} 个，请确保唯一")
    control = controls[0]
    if control.getparent() is None or control.getparent().tag not in {W + "body", W + "tc"}:
        raise ValueError(f"方案原文块目标控件 {tag} 必须是正文或表格单元格级内容控件")
    return control


def _standard_field_code(mapping: dict[str, Any]) -> str:
    return str(mapping.get("standardFieldCode") or mapping.get("fieldCode") or "")


def copy_protocol_raw_blocks(parts: dict[str, tuple[Any, bytes]], document: etree._Element,
                             mappings: list[dict[str, Any]], protocol_rules: list[dict[str, Any]],
                             protocol_path: Path | None) -> None:
    rules = {str(rule.get("fieldCode")): rule for rule in protocol_rules
             if rule.get("enabled", True) and rule.get("sourceType") == "PROTOCOL"
             and (rule.get("config") or {}).get("mode") == "RAW_BLOCK"}
    selected = [mapping for mapping in mappings if mapping.get("enabled", True)
                and mapping.get("controlTag")
                and _standard_field_code(mapping) in rules]
    if not selected:
        return
    if protocol_path is None or not protocol_path.is_file():
        raise ValueError("报告配置了方案原文块字段，但没有关联有效的 Word 方案文件")
    with zipfile.ZipFile(protocol_path) as source:
        source_root = etree.fromstring(source.read("word/document.xml"))
        source_body = source_root.find(W + "body")
        if source_body is None:
            raise ValueError("方案缺少 Word 正文，无法复制原文块")
        source_blocks = _direct_blocks(source_body)
        structure_blocks = read_protocol_structure(protocol_path)
        if len(source_blocks) != len(structure_blocks):
            raise ValueError("方案包含暂不支持的嵌套内容控件，无法安全定位原文块")
        for mapping in selected:
            field_code = _standard_field_code(mapping)
            rule = rules[field_code]
            config = rule.get("config") or {}
            start, end = _block_range(protocol_path, config)
            if end > len(source_blocks):
                raise ValueError("方案结构与 Word 正文块不一致，无法安全复制")
            selected_blocks = source_blocks[start:end]
            label = str(config.get("sectionPattern") or field_code)
            _check_self_contained(selected_blocks, label)
            copied = _copy_blocks(selected_blocks)
            _copy_styles(copied, source, parts)
            control = _target_control(document, str(mapping["controlTag"]))
            content = control.find(W + "sdtContent")
            if content is None:
                raise ValueError(f"目标内容控件 {mapping['controlTag']} 缺少 sdtContent")
            for child in list(content):
                content.remove(child)
            for block in copied:
                content.append(block)
            logger.info("方案原文块复制完成 field=%s target=%s", field_code, mapping["controlTag"])
