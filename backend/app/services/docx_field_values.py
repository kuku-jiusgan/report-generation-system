"""从数据源取值、按字段规则格式化，以及计算字段求值。

拆分自 mapped_docx_generator：取值/计算与 Word 排版是两件事，
拆开后生成器只负责往文档里写，本模块只负责算出该写什么。
"""

import re
from typing import Any

from lxml import etree

from .calculation_engine import CalculationError, evaluate_formula


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def tag_of(control: etree._Element) -> str:
    values = control.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
    return str(values[0]) if values else ""


def set_control_text(control: etree._Element, value: Any) -> None:
    content = control.find(W + "sdtContent")
    texts = control.xpath("./w:sdtContent//w:t", namespaces=NS)
    if not texts:
        if content is None:
            return
        paragraph = etree.SubElement(content, W + "p")
        run = etree.SubElement(paragraph, W + "r")
        texts = [etree.SubElement(run, W + "t")]
    text = "" if value is None else str(value)
    texts[0].text = text.split("\n")[0]
    for line_break in content.xpath(".//w:br | .//w:cr", namespaces=NS) if content is not None else []:
        line_break.getparent().remove(line_break)
    if "\n" in text:
        previous = texts[0]
        for line in text.split("\n")[1:]:
            line_break = etree.Element(W + "br")
            previous.addnext(line_break)
            next_text = etree.Element(W + "t")
            next_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            next_text.text = line
            line_break.addnext(next_text)
            previous = next_text
    for text in texts[1:]:
        text.text = ""
    if content is not None:
        _drop_blank_paragraphs(content)


def _drop_blank_paragraphs(content: etree._Element) -> None:
    """控件里的值只写进第一个段落，其余段落填完值就是空的，留着会在单元格里多出空行。

    模板作者常把过长的文字（例如"三重四极/液质联用仪"）手动折成两段，绑定字段时
    这些段落一起被包进控件；它们属于占位内容而不是模板固定文字，删掉才不会每行多一个空行。
    控件外的前后缀不在 sdtContent 里，不受影响。至少保留一个段落，避免单元格没有段落。
    """
    paragraphs = content.findall(W + "p")
    if len(paragraphs) < 2:
        return
    filled = [item for item in paragraphs
              if "".join(item.xpath(".//w:t/text()", namespaces=NS)).strip()
              or item.xpath(".//w:drawing | .//w:pict", namespaces=NS)]
    for paragraph in paragraphs[1:] if not filled else paragraphs:
        if paragraph not in filled:
            content.remove(paragraph)


def path_value(data: Any, path: str) -> Any:
    if not path.startswith("$."):
        return None
    current = data
    for part in path[2:].split("."):
        if part.endswith("[*]"):
            key = part[:-3]
            current = current.get(key) if isinstance(current, dict) else None
            if not isinstance(current, list):
                return None
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def repeat_source(path: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"\$\.([A-Za-z0-9_]+)\[\*\](?:\.(.+))?", path)
    return (match.group(1), match.group(2) or "") if match else None


def record_value(record: Any, field_path: str) -> Any:
    """按相对路径取值；路径里的 `[*]` 表示进入记录内的明细数组，返回该层的取值列表。"""
    current = record
    if not field_path:
        return current
    for part in field_path.split("."):
        key, many = (part[:-3], True) if part.endswith("[*]") else (part, False)
        if isinstance(current, list):
            current = [item.get(key) if isinstance(item, dict) else None for item in current]
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if many and not isinstance(current, list):
            return None
    return current


def payload_for_mapping(mapping: dict[str, Any], payload: dict[str, Any],
                         report_data: dict[str, Any]) -> dict[str, Any]:
    field_sources = report_data.get("field_sources", {}) if isinstance(report_data, dict) else {}
    source_meta = field_sources.get(str(mapping.get("standardFieldCode") or ""), {})
    source_type = str(source_meta.get("type") or mapping.get("sourceType") or "LIMS").upper()
    payloads = report_data.get("source_payloads", {}) if isinstance(report_data, dict) else {}
    if source_type == "PROTOCOL":
        return payloads.get("PROTOCOL", {})
    if source_type == "EXCEL":
        return payloads.get("EXCEL", {}) if isinstance(payloads.get("EXCEL"), dict) else {}
    if source_type == "PDF":
        return payloads.get("PDF", {}) if isinstance(payloads.get("PDF"), dict) else {}
    if source_type == "LIMS":
        source_payload = payloads.get("LIMS")
        return source_payload if isinstance(source_payload, dict) else payload
    return payload


def mapping_source_path(mapping: dict[str, Any]) -> str:
    """字段的取值路径。由标准字段目录解析后放在映射上，这里不再有第二个来源。"""
    return str(mapping.get("sourcePath") or "")


def source_mapping_value(mapping: dict[str, Any], payload: dict[str, Any],
                          report_data: dict[str, Any]) -> Any:
    source = report_data.get("field_sources", {}).get(str(mapping.get("standardFieldCode") or ""), {})
    if source.get("type") == "PROTOCOL" and source.get("status") == "ERROR":
        return ""
    path = mapping_source_path(mapping)
    source_payload = payload_for_mapping(mapping, payload, report_data)
    repeat = repeat_source(path)
    if repeat:
        records = source_payload.get(repeat[0])
        if not isinstance(records, list):
            return []
        return [record_value(record, repeat[1]) for record in records]
    return path_value(source_payload, path)


def is_formula_calculation(mapping: dict[str, Any]) -> bool:
    return mapping.get("sourceType") == "CALCULATED" and bool(mapping.get("calculationExpression"))


def calculated_values(mappings: list[dict[str, Any]], payload: dict[str, Any],
                       report_data: dict[str, Any]) -> dict[str, Any]:
    values = {
        str(mapping.get("fieldCode")): source_mapping_value(mapping, payload, report_data)
        for mapping in mappings
        if mapping.get("fieldCode") and not is_formula_calculation(mapping)
    }
    pending = {
        str(mapping.get("fieldCode")): mapping
        for mapping in mappings
        if is_formula_calculation(mapping)
        and mapping.get("calculationExpression")
        and mapping.get("calculationScope", "REPORT") != "CURRENT_ROW"
    }
    while pending:
        progressed = False
        for code, mapping in list(pending.items()):
            dependencies = list(mapping.get("calculationDependencies", []))
            waiting = [value for value in dependencies if value in pending]
            if waiting:
                continue
            try:
                values[code] = evaluate_formula(
                    str(mapping.get("calculationExpression") or ""),
                    dependencies,
                    values,
                    int(mapping.get("calculationPrecision", 2)),
                    str(mapping.get("calculationNullBehavior", "ERROR")),
                )
            except CalculationError as error:
                raise CalculationError(f"计算字段“{mapping.get('wordLabel', code)}”失败：{error}") from error
            pending.pop(code)
            progressed = True
        if not progressed:
            raise CalculationError(f"计算字段依赖无法解析：{', '.join(pending)}")
    return values


def row_calculated_values(
    group: list[dict[str, Any]],
    record: dict[str, Any],
    global_values: dict[str, Any],
    report_data: dict[str, Any],
) -> dict[str, Any]:
    values = dict(global_values)
    for mapping in group:
        if is_formula_calculation(mapping) or not mapping.get("fieldCode"):
            continue
        # 行内取值必须与行填充使用同一有效路径，否则字段被系统规则改道后行值错位
        repeat = repeat_source(mapping_source_path(mapping))
        values[str(mapping["fieldCode"])] = record_value(record, repeat[1]) if repeat else values.get(
            str(mapping["fieldCode"])
        )
    pending = {
        str(mapping.get("fieldCode")): mapping
        for mapping in group
        if is_formula_calculation(mapping)
        and mapping.get("calculationExpression")
        and mapping.get("calculationScope", "REPORT") == "CURRENT_ROW"
    }
    while pending:
        progressed = False
        for code, mapping in list(pending.items()):
            dependencies = list(mapping.get("calculationDependencies", []))
            if any(value in pending for value in dependencies):
                continue
            values[code] = evaluate_formula(
                str(mapping.get("calculationExpression") or ""),
                dependencies,
                values,
                int(mapping.get("calculationPrecision", 2)),
                str(mapping.get("calculationNullBehavior", "ERROR")),
            )
            pending.pop(code)
            progressed = True
        if not progressed:
            raise CalculationError(f"行内计算字段依赖无法解析：{', '.join(pending)}")
    return values


def format_value(value: Any, mapping: dict[str, Any], use_empty_rule: bool = True) -> str:
    # 填充规则优先从映射规则取，如果没有则从标准字段取
    fill_rule = str(mapping.get("fillRule") or mapping.get("standardFieldFillRule") or "")

    if value in (None, ""):
        return "-" if use_empty_rule and "EMPTY_AS_DASH" in fill_rule else ""
    if fill_rule == "VERSION_2_DIGITS":
        try:
            return f"{int(value):02d}"
        except (TypeError, ValueError):
            pass

    # APPEND_SUFFIX:后缀文字 — 在字段值后面拼接固定文字
    # ponytail: 解决 Word 控件无法包裹部分文本的限制；用于表标题等场景
    if fill_rule.startswith("APPEND_SUFFIX:"):
        suffix = fill_rule[len("APPEND_SUFFIX:"):]
        return f"{value}{suffix}"

    output_format = str(mapping.get("standardFieldOutputFormat") or "")
    if output_format.isdigit() and mapping.get("standardFieldDataType") in {"decimal", "number"}:
        try:
            return f"{float(value):.{int(output_format)}f}"
        except (TypeError, ValueError):
            pass
    return str(value)
