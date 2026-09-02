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
    texts = control.xpath("./w:sdtContent//w:t", namespaces=NS)
    if not texts:
        content = control.find(W + "sdtContent")
        if content is None:
            return
        paragraph = etree.SubElement(content, W + "p")
        run = etree.SubElement(paragraph, W + "r")
        texts = [etree.SubElement(run, W + "t")]
    texts[0].text = "" if value is None else str(value)
    for text in texts[1:]:
        text.text = ""


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
    current = record
    if not field_path:
        return current
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def payload_for_mapping(mapping: dict[str, Any], payload: dict[str, Any],
                         report_data: dict[str, Any]) -> dict[str, Any]:
    field_sources = report_data.get("field_sources", {}) if isinstance(report_data, dict) else {}
    source_meta = field_sources.get(str(mapping.get("standardFieldCode") or ""), {})
    source_type = str(source_meta.get("type") or mapping.get("sourceType") or "LIMS").upper()
    payloads = report_data.get("source_payloads", {}) if isinstance(report_data, dict) else {}
    if source_type == "EXCEL":
        return payloads.get("EXCEL", {}) if isinstance(payloads.get("EXCEL"), dict) else {}
    if source_type == "PDF":
        return payloads.get("PDF", {}) if isinstance(payloads.get("PDF"), dict) else {}
    if source_type == "LIMS":
        source_payload = payloads.get("LIMS")
        return source_payload if isinstance(source_payload, dict) else payload
    return payload


def mapping_source_path(mapping: dict[str, Any], report_data: dict[str, Any]) -> str:
    field_sources = report_data.get("field_sources", {}) if isinstance(report_data, dict) else {}
    source_meta = field_sources.get(str(mapping.get("standardFieldCode") or ""), {})
    return str(source_meta.get("sourcePath") or mapping.get("sourcePath") or "")


def source_mapping_value(mapping: dict[str, Any], payload: dict[str, Any],
                          report_data: dict[str, Any]) -> Any:
    path = mapping_source_path(mapping, report_data)
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
        repeat = repeat_source(mapping_source_path(mapping, report_data))
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
    if value in (None, ""):
        return "-" if use_empty_rule and "EMPTY_AS_DASH" in mapping.get("fillRule", "") else ""
    if mapping.get("fillRule") == "VERSION_2_DIGITS":
        try:
            return f"{int(value):02d}"
        except (TypeError, ValueError):
            pass
    output_format = str(mapping.get("standardFieldOutputFormat") or "")
    if output_format.isdigit() and mapping.get("standardFieldDataType") in {"decimal", "number"}:
        try:
            return f"{float(value):.{int(output_format)}f}"
        except (TypeError, ValueError):
            pass
    return str(value)
