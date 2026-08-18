import copy
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .calculation_engine import CalculationError, evaluate_formula
from .docx_language import normalize_part_languages
from .docx_images import embed_image_controls
from .docx_matrix import fill_matrix_tables as _fill_matrix_table
from .report_fields import REPORT_FIELD_BINDINGS


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W_NS, "r": R_NS}
W = f"{{{W_NS}}}"


REPORT_TAGS = REPORT_FIELD_BINDINGS
STRUCTURED_REPEAT_SOURCES = {
    "approval", "samples", "referenceStandards", "instruments", "columns", "reagents", "weighings",
}
TABLE_SOURCE_OVERRIDES = {
    "T12": "systemSuitabilitySolutions", "T14": "specificitySolutions", "T16": "lodSolutions",
    "T21": "repeatabilitySolutions", "T23": "intermediatePrecisionSolutions",
    "T24": "intermediateLinearityPreparation", "T25": "intermediateLinearity",
    "T27": "accuracySolutions",
    "T30": "stabilitySolutions",
    "T32": "robustnessSolutions",
}
MATRIX_TABLES = {"T20", "T25"}
PRESERVED_ROW_LABELS = ("RSD", "结论", "平均", "回归方程", "相关系数", "斜率", "截距")


def _tag(control: etree._Element) -> str:
    values = control.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
    return str(values[0]) if values else ""


def _set_control_text(control: etree._Element, value: Any) -> None:
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


def _path_value(data: Any, path: str) -> Any:
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


def _repeat_source(path: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"\$\.([A-Za-z0-9_]+)\[\*\](?:\.(.+))?", path)
    return (match.group(1), match.group(2) or "") if match else None


def _record_value(record: Any, field_path: str) -> Any:
    current = record
    if not field_path:
        return current
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _payload_for_mapping(mapping: dict[str, Any], payload: dict[str, Any],
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


def _mapping_source_path(mapping: dict[str, Any], report_data: dict[str, Any]) -> str:
    field_sources = report_data.get("field_sources", {}) if isinstance(report_data, dict) else {}
    source_meta = field_sources.get(str(mapping.get("standardFieldCode") or ""), {})
    return str(source_meta.get("sourcePath") or mapping.get("sourcePath") or "")


def _source_mapping_value(mapping: dict[str, Any], payload: dict[str, Any],
                          report_data: dict[str, Any]) -> Any:
    path = _mapping_source_path(mapping, report_data)
    source_payload = _payload_for_mapping(mapping, payload, report_data)
    repeat = _repeat_source(path)
    if repeat:
        records = source_payload.get(repeat[0])
        if not isinstance(records, list):
            return []
        return [_record_value(record, repeat[1]) for record in records]
    return _path_value(source_payload, path)


def _is_formula_calculation(mapping: dict[str, Any]) -> bool:
    return mapping.get("sourceType") == "CALCULATED" and bool(mapping.get("calculationExpression"))


def _calculated_values(mappings: list[dict[str, Any]], payload: dict[str, Any],
                       report_data: dict[str, Any]) -> dict[str, Any]:
    values = {
        str(mapping.get("fieldCode")): _source_mapping_value(mapping, payload, report_data)
        for mapping in mappings
        if mapping.get("fieldCode") and not _is_formula_calculation(mapping)
    }
    pending = {
        str(mapping.get("fieldCode")): mapping
        for mapping in mappings
        if _is_formula_calculation(mapping)
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


def _row_calculated_values(
    group: list[dict[str, Any]],
    record: dict[str, Any],
    global_values: dict[str, Any],
) -> dict[str, Any]:
    values = dict(global_values)
    for mapping in group:
        if _is_formula_calculation(mapping) or not mapping.get("fieldCode"):
            continue
        repeat = _repeat_source(str(mapping.get("sourcePath") or ""))
        values[str(mapping["fieldCode"])] = _record_value(record, repeat[1]) if repeat else values.get(
            str(mapping["fieldCode"])
        )
    pending = {
        str(mapping.get("fieldCode")): mapping
        for mapping in group
        if _is_formula_calculation(mapping)
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


def _prepare_repeat_records(records: list[dict[str, Any]], group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = list(records)
    dedup_key = next((str(item.get("blockDedupKey") or "") for item in group if item.get("blockDedupKey")), "")
    if dedup_key:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for record in prepared:
            identity = repr(_record_value(record, dedup_key))
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(record)
        prepared = unique
    sort_rule = next((str(item.get("blockSortRule") or "") for item in group if item.get("blockSortRule")), "")
    rules: list[tuple[str, bool]] = []
    for expression in sort_rule.split(","):
        parts = expression.strip().split()
        if parts:
            rules.append((parts[0], len(parts) > 1 and parts[1].upper() == "DESC"))
    for field, reverse in reversed(rules):
        prepared.sort(key=lambda item: str(_record_value(item, field) or ""), reverse=reverse)
    return prepared


def _set_vertical_merge(cell: etree._Element, restart: bool) -> None:
    properties = cell.find(W + "tcPr")
    if properties is None:
        properties = etree.Element(W + "tcPr")
        cell.insert(0, properties)
    for existing in properties.findall(W + "vMerge"):
        properties.remove(existing)
    merge = etree.SubElement(properties, W + "vMerge")
    if restart:
        merge.set(W + "val", "restart")


def _cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS)).strip()


def _set_cell_text(cell: etree._Element, value: Any) -> None:
    texts = cell.xpath(".//w:t", namespaces=NS)
    if not texts:
        paragraph = cell.find(W + "p")
        if paragraph is None:
            paragraph = etree.SubElement(cell, W + "p")
        run = etree.SubElement(paragraph, W + "r")
        texts = [etree.SubElement(run, W + "t")]
    texts[0].text = "" if value is None else str(value)
    for text in texts[1:]:
        text.text = ""


def _is_preserved_summary_row(row: etree._Element) -> bool:
    cells = row.xpath("./w:tc", namespaces=NS)
    label = _cell_text(cells[0]) if cells else ""
    return any(label.startswith(prefix) for prefix in PRESERVED_ROW_LABELS)


def _clear_unmapped_summary_cells(row: etree._Element, direct_tags: set[str]) -> None:
    cells = row.xpath("./w:tc", namespaces=NS)
    for cell in cells[1:]:
        cell_tags = set(cell.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
        if not cell_tags.intersection(direct_tags):
            _set_cell_text(cell, "")


def _format_value(value: Any, mapping: dict[str, Any], use_empty_rule: bool = True) -> str:
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


def _clear_mapped_controls(roots: dict[str, etree._Element], mappings: list[dict[str, Any]]) -> None:
    clear_tags = {
        item.get("controlTag", "")
        for item in mappings
        if item.get("enabled", True) and item.get("sourceType") not in {"FIXED"}
    }
    for root in roots.values():
        for control in root.xpath(".//w:sdt", namespaces=NS):
            if _tag(control) in clear_tags:
                _set_control_text(control, "")
                cells = control.xpath("ancestor::w:tc[1]", namespaces=NS)
                if cells:
                    for text in cells[0].xpath(".//w:t", namespaces=NS):
                        owners = text.xpath("ancestor::w:sdt[1]", namespaces=NS)
                        if not owners or _tag(owners[0]) not in clear_tags:
                            text.text = ""


def _fill_direct_controls(roots: dict[str, etree._Element], mappings: list[dict[str, Any]],
                          payload: dict[str, Any], report_data: dict[str, Any],
                          calculated_values: dict[str, Any]) -> None:
    values: dict[str, str] = {}
    for mapping in mappings:
        tag = mapping.get("controlTag", "")
        if not tag or not mapping.get("enabled", True) or mapping.get("repeatType") == "ROW":
            continue
        value = (
            calculated_values.get(str(mapping.get("fieldCode")))
            if _is_formula_calculation(mapping)
            else _source_mapping_value(mapping, payload, report_data)
        )
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if value is not None and not isinstance(value, (dict, list)):
            values[tag] = _format_value(value, mapping)
    for tag, field in REPORT_TAGS.items():
        if report_data.get(field) not in (None, ""):
            values[tag] = str(report_data[field])
    for root in roots.values():
        for control in root.xpath(".//w:sdt", namespaces=NS):
            tag = _tag(control)
            if tag in values:
                _set_control_text(control, values[tag])


def _fill_repeat_rows(document: etree._Element, mappings: list[dict[str, Any]], payload: dict[str, Any],
                      report_data: dict[str, Any], calculated_values: dict[str, Any]) -> None:
    groups: dict[str, list[dict[str, Any]]] = {}
    for mapping in mappings:
        if mapping.get("enabled", True) and mapping.get("repeatType") == "ROW" and mapping.get("tableNo"):
            groups.setdefault(mapping["tableNo"], []).append(mapping)

    for table_no, group in groups.items():
        explicit_source = next((_repeat_source(item.get("blockSourcePath", "")) for item in group
                                if _repeat_source(item.get("blockSourcePath", ""))), None)
        source = explicit_source or next((_repeat_source(_mapping_source_path(item, report_data)) for item in group
                                          if _repeat_source(_mapping_source_path(item, report_data))), None)
        if not source:
            continue
        if not explicit_source:
            source = (TABLE_SOURCE_OVERRIDES.get(table_no, source[0]), source[1])
        source_mapping = next((item for item in group if _repeat_source(_mapping_source_path(item, report_data))), group[0])
        source_payload = _payload_for_mapping(source_mapping, payload, report_data)
        records = source_payload.get(source[0])
        if not isinstance(records, list):
            records = []
        records = _prepare_repeat_records(records, group)
        if table_no in MATRIX_TABLES:
            _fill_matrix_table(document, table_no, records)
            continue
        bookmarks = document.xpath(
            f".//w:bookmarkStart[@w:name='repeat_{table_no.lower()}_row']", namespaces=NS
        )
        if not bookmarks:
            continue
        prototype = bookmarks[0].getparent()
        parent = prototype.getparent()
        insert_at = parent.index(prototype)
        group_tags = {item.get("controlTag", "") for item in group}
        # Text outside a content control in an otherwise mapped cell is intentional
        # template content (for example a fixed company suffix). Only clear cells
        # that have no mapped control at all; clearing every unowned run erased such
        # static prefixes and suffixes from generated repeat rows.
        for cell in prototype.xpath("./w:tc", namespaces=NS):
            cell_tags = set(cell.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
            if cell_tags & group_tags:
                continue
            for text in cell.xpath(".//w:t", namespaces=NS):
                text.text = ""
        direct_tags = {
            item.get("controlTag", "") for item in mappings
            if item.get("controlTag") and item.get("repeatType") != "ROW"
        }
        for old_row in list(parent)[insert_at + 1:]:
            if old_row.tag != W + "tr":
                continue
            row_tags = set(old_row.xpath(".//w:sdtPr/w:tag/@w:val", namespaces=NS))
            if row_tags & direct_tags:
                continue
            if _is_preserved_summary_row(old_row):
                _clear_unmapped_summary_cells(old_row, direct_tags)
                continue
            parent.remove(old_row)
        empty_behavior = next((item.get("blockEmptyBehavior") for item in group
                               if item.get("blockEmptyBehavior")), "KEEP")
        if not records and empty_behavior == "HIDE":
            parent.remove(prototype)
            continue
        rows = [prototype] if records else []
        if not records:
            for control in prototype.xpath(".//w:sdt", namespaces=NS):
                _set_control_text(control, "")
        for offset in range(1, len(records)):
            cloned = copy.deepcopy(prototype)
            for bookmark in cloned.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
                bookmark.getparent().remove(bookmark)
            parent.insert(insert_at + offset, cloned)
            rows.append(cloned)
        for row, record in zip(rows, records):
            controls = {_tag(control): control for control in row.xpath(".//w:sdt", namespaces=NS)}
            row_values = _row_calculated_values(group, record, calculated_values)
            for mapping in group:
                control = controls.get(mapping.get("controlTag", ""))
                if control is not None:
                    if _is_formula_calculation(mapping):
                        value = row_values.get(str(mapping.get("fieldCode")))
                    else:
                        repeat_path = _repeat_source(_mapping_source_path(mapping, report_data))
                        if not repeat_path or TABLE_SOURCE_OVERRIDES.get(table_no, repeat_path[0]) != source[0]:
                            continue
                        value = _record_value(record, repeat_path[1])
                    _set_control_text(control, _format_value(value, mapping))
        if len(rows) > 1:
            block_merge = next((item.get("blockMergeRule") for item in group
                                if item.get("blockMergeRule")), "NONE")
            for mapping in group:
                if block_merge != "VERTICAL_BY_VALUE" and mapping.get("mergeRule") != "VERTICAL_BY_VALUE":
                    continue
                tag = mapping.get("controlTag", "")
                previous: Any = object()
                previous_cell: etree._Element | None = None
                for row, record in zip(rows, records):
                    repeat_path = _repeat_source(mapping.get("sourcePath", ""))
                    value = _record_value(record, repeat_path[1]) if repeat_path else None
                    controls = {_tag(control): control for control in row.xpath(".//w:sdt", namespaces=NS)}
                    control = controls.get(tag)
                    cell = control.xpath("ancestor::w:tc[1]", namespaces=NS)[0] if control is not None else None
                    if cell is not None and value not in (None, "") and value == previous and previous_cell is not None:
                        _set_vertical_merge(previous_cell, True)
                        _set_vertical_merge(cell, False)
                        _set_control_text(control, "")
                    else:
                        previous_cell = cell
                    previous = value


def _clear_external_table_objects(document: etree._Element) -> set[str]:
    relationship_ids: set[str] = set()
    tables = document.xpath("./w:body/w:tbl", namespaces=NS)
    for table_number in (3, 20, 24):
        if table_number > len(tables):
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
                      payload: dict[str, Any] | None = None, report_data: dict[str, Any] | None = None) -> None:
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
    removed_relationship_ids = _clear_external_table_objects(roots["word/document.xml"])
    _remove_relationship_parts(parts, removed_relationship_ids)

    normalized_payload = payload or {}
    normalized_report = report_data or {}
    if normalized_payload or normalized_report:
        calculated_values = _calculated_values(active_mappings, normalized_payload, normalized_report)
        _fill_direct_controls(
            roots, active_mappings, normalized_payload, normalized_report, calculated_values
        )
        _fill_repeat_rows(
            roots["word/document.xml"], active_mappings, normalized_payload, normalized_report, calculated_values
        )

    embed_image_controls(parts, roots, active_mappings)

    for name, root in roots.items():
        parts[name] = (parts[name][0], etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        ))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for info, content in parts.values():
            target.writestr(info, content)
