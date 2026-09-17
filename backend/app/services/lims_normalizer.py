import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from lxml import html

from .lims_configured_extractor import apply_configured_extraction
from .lims_table_utils import cell_value, column_value, impurity_columns, limit_calculation_records, validation_summary_columns
from .lims_validation import sort_validation_summary, validation_code
from .configured_group_parser import apply_configured_group_tables


COLLECTION_LABELS = {
    "samples": "供试品",
    "referenceStandards": "对照品",
    "instruments": "仪器",
    "columns": "色谱柱",
    "reagents": "试剂",
    "weighings": "称量记录",
    "impurity": "杂质与限度",
    "limit": "限度计算",
    "validationSummary": "验证标准与结论",
    "solutions": "溶液配制",
    "methodParameters": "方法参数",
    "systemSuitability": "系统适用性",
    "specificity": "专属性",
    "jiancexian": "检测限",
    "loq": "定量限",
    "linearityPreparation": "线性溶液",
    "linearity": "线性与范围",
    "repeatability": "重复性",
    "intermediatePrecision": "中间精密度",
    "blankAmount": "空白量",
    "accuracy": "准确度",
    "solutionStability": "溶液稳定性",
    "robustnessSpecificity": "耐用性专属性",
    "robustnessSequence": "耐用性进样",
    "robustnessResult": "耐用性结果",
    "sampleResults": "样品结果",
    "formulas": "计算公式",
    "conclusions": "实验结论",
}

COLLECTION_ORDER = list(COLLECTION_LABELS)
SOLUTION_VIEW_CODES = {
    "systemSuitabilitySolutions": "systemSuitability",
    "specificitySolutions": "specificity",
    "lodSolutions": "jiancexian",
    "repeatabilitySolutions": "repeatability",
    "intermediatePrecisionSolutions": "intermediatePrecision",
    "accuracySolutions": "accuracy",
    "stabilitySolutions": "solutionStability",
    "robustnessSolutions": "robustness",
}
DERIVED_COLLECTION_CODES = frozenset({
    *SOLUTION_VIEW_CODES, "intermediateLinearityPreparation", "intermediateLinearity",
})


def record_collection_codes(groups: list[dict[str, Any]] | None = None) -> list[str]:
    """Return built-in and configured multi-row collections in stable order."""
    configured = [
        str(group.get("groupCode") or "").strip()
        for group in groups or []
        if group.get("enabled", True) and str(group.get("cardinality") or "ONE").upper() == "MANY"
        and str(group.get("groupCode") or "").strip() not in DERIVED_COLLECTION_CODES
    ]
    return list(dict.fromkeys([*COLLECTION_ORDER, *(code for code in configured if code)]))


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _at(row: list[str], index: int) -> str:
    return _clean(row[index]) if index < len(row) else ""


def _semantic(value: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", _clean(value)).replace("（", "(").replace("）", ")")


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _business_content(item: dict[str, Any]) -> dict[str, Any]:
    """Return values that describe the business record, without source metadata."""
    return {key: value for key, value in item.items() if key not in {"evidence", "sourceRecordId"}}


def _content_hash(item: dict[str, Any]) -> str:
    """Hash business content so equivalent records from different LIMS rows deduplicate."""
    return _hash(_business_content(item))


def _comparison_content(item: dict[str, Any]) -> dict[str, Any]:
    """Return structured business values for conflict comparison."""
    return _business_content(item)


def _find_column(headers: list[str], patterns: tuple[str, ...]) -> int | None:
    for pattern in patterns:
        for index, header in enumerate(headers):
            if header == pattern:
                return index
    for pattern in patterns:
        for index, header in enumerate(headers):
            if pattern in header:
                return index
    return None


def _table_grid(table: html.HtmlElement) -> list[list[str]]:
    grid: list[list[str]] = []
    spans: dict[int, tuple[int, str]] = {}
    for tr in table.xpath("./thead/tr|./tbody/tr|./tfoot/tr|./tr"):
        row: list[str] = []
        column = 0

        def consume_spans() -> None:
            nonlocal column
            while column in spans:
                remaining, text = spans[column]
                row.append(text)
                if remaining <= 1:
                    del spans[column]
                else:
                    spans[column] = (remaining - 1, text)
                column += 1

        consume_spans()
        for cell in tr.xpath("./th|./td"):
            consume_spans()
            text = cell_value(cell)
            colspan = max(1, int(cell.get("colspan") or 1))
            rowspan = max(1, int(cell.get("rowspan") or 1))
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    spans[column] = (rowspan - 1, text)
                column += 1
        consume_spans()
        if any(row):
            grid.append(row)
    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid]


def _evidence(instance: dict[str, Any], rich_text: dict[str, Any], table_index: int,
              headers: list[str]) -> dict[str, Any]:
    source = dict(rich_text.get("evidence") or {})
    source.update({
        "type": "LIMS",
        "instanceId": instance["instanceId"],
        "instanceTitle": instance.get("title", ""),
        "sectionPath": rich_text.get("sectionPath", []),
        "richTextId": rich_text.get("id"),
        "tableIndex": table_index,
        "headers": headers,
    })
    return source


def _record(values: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    return {**values, "evidence": evidence}


def _is_system_suitability_detail(value: Any) -> bool:
    sequence = _clean(value)
    return bool(sequence) and not re.search(r"结论|RSD|平均|标准差|置信区间", sequence, re.IGNORECASE)


def _rows_as_fields(rows: list[list[str]], evidence: dict[str, Any], start: int = 1) -> list[dict[str, Any]]:
    output = []
    for row in rows[start:]:
        if not any(_clean(cell) for cell in row):
            continue
        output.append(_record({f"field{index + 1}": _clean(value) for index, value in enumerate(row)}, evidence))
    return output


def _classify_table(instance: dict[str, Any], rich_text: dict[str, Any], table_index: int,
                    rows: list[list[str]], result: dict[str, list[dict[str, Any]]],
                    parser_profiles: dict[str, list[dict[str, Any]]] | None = None) -> bool:
    if not rows:
        return False
    header = "|".join(rows[0])
    first_three = "|".join("|".join(row) for row in rows[:3])
    path = ">".join(rich_text.get("sectionPath", []))
    evidence = _evidence(instance, rich_text, table_index, rows[0])
    def profile_enabled(profile: str) -> bool:
        configured = (parser_profiles or {}).get(profile)
        if configured is None:
            return True
        for rule in configured:
            if not rule.get("enabled", True):
                continue
            section_pattern = str(rule.get("sectionPattern") or "")
            header_pattern = str(rule.get("headerPattern") or "")
            try:
                section_matches = not section_pattern or re.search(section_pattern, path, re.IGNORECASE)
                header_matches = not header_pattern or re.search(header_pattern, first_three, re.IGNORECASE)
            except re.error:
                continue
            if section_matches and header_matches:
                return True
        return False

    impurity_indexes = impurity_columns(rows[0])
    if profile_enabled("IMPURITY_LIMIT_TABLE") and impurity_indexes:
        for row in rows[1:]:
            if not row or not _clean(row[0]) or _clean(row[0]) in {"序号", "No."}:
                continue
            name = column_value(row, impurity_indexes["name"])
            if not name:
                continue
            cas = column_value(row, impurity_indexes["cas"])
            structure = column_value(row, impurity_indexes["structure"])
            limit = column_value(row, impurity_indexes["limit"])
            result["impurity"].append(_record({"impurityName": name, "field2": cas,
                                                "field3": structure, "field4": limit}, evidence))
        return True

    limit_records = limit_calculation_records(rows)
    if profile_enabled("LIMIT_CALCULATION_TABLE") and limit_records:
        result["limit"].extend(_record(values, evidence) for values in limit_records)
        return True

    validation_indexes = validation_summary_columns(rows[0])
    if profile_enabled("VALIDATION_SUMMARY_TABLE") and validation_indexes:
        for row in rows[1:]:
            name = column_value(row, validation_indexes["project"])
            criteria = column_value(row, validation_indexes["criteria"])
            if name and criteria:
                result["validationSummary"].append(_record({"field1": name,
                                                              "validationItemCode": validation_code(name, True),
                                                              "acceptanceCriteria": criteria,
                                                              "conclusion": ""}, evidence))
        return True

    if profile_enabled("SOLUTION_PREPARATION_TABLE") and (("配制方法" in header and ("溶液名称" in header or "名称" in header)) or header.startswith("名称|溶液配制")):
        headers = [_clean(value) for value in rows[0]]
        # 列定位必须与进入条件可互相印证：精确优先、子串兜底；定位失败则不认领该表
        name_index = _find_column(headers, ("溶液名称",))
        if name_index is None:
            name_index = next((index for index, value in enumerate(headers) if value == "名称"), None)
        preparation_index = _find_column(headers, ("配制方法",))
        if name_index is None or preparation_index is None:
            return False
        project_index = headers.index("验证项目") if "验证项目" in headers else None
        project = ""
        for row in rows[1:]:
            if len(row) < 2:
                continue
            if project_index is not None and _at(row, project_index):
                project = _at(row, project_index)
            name, preparation = _at(row, name_index), _at(row, preparation_index)
            if not name or not preparation or name in {"溶液名称", "名称"}:
                continue
            result["solutions"].append(_record({
                "name": name, "preparation": preparation,
                "validationCode": validation_code(project or instance.get("title", "")) or "shared",
                "validationProject": project,
            }, evidence))
        return True

    if profile_enabled("METHOD_PARAMETER_TABLE") and ("仪器方法" in path or "分析方法" in header or ("项目" in header and "参数" in header)):
        for row in rows[1:]:
            values = [_clean(value) for value in row]
            values = [value for index, value in enumerate(values) if value and (index == 0 or value != values[index - 1])]
            if len(values) >= 2:
                if len(values) == 2:
                    values.insert(0, "方法参数")
                result["methodParameters"].append(_record({"field1": values[0], "field2": values[1],
                                                             "field3": "；".join(values[2:])}, evidence))
        return True

    if "杂质名称" in header and "信噪比-1" in header and "检测限" in header:
        for row in rows[1:]:
            if _clean(row[0]) == "结论":
                if result["jiancexian"]:
                    result["jiancexian"][-1]["conclusion"] = _clean(row[1] if len(row) > 1 else "")
                continue
            if _clean(row[0]):
                result["jiancexian"].append(_record({"name": _clean(row[0]), "field2": _at(row, 1),
                    "field3": _at(row, 2), "field4": _at(row, 3), "field5": _at(row, 4),
                    "field6": _at(row, 5), "field7": _at(row, 6), "conclusion": ""}, evidence))
        return True

    if "信噪比" in header and "定量限" in header and "峰面积" in header:
        for row in rows[1:]:
            if _clean(row[0]) and _clean(row[0]) != "结论":
                result["loq"].append(_record({"sequence": _clean(row[0]), "field2": _at(row, 1),
                    "peakArea": _at(row, 2), "field4": _at(row, 3), "field5": _at(row, 4),
                    "field6": _at(row, 5), "field7": _at(row, 6)}, evidence))
        return True

    if "溶液名称" in header and "C1" in header and "峰面积" in first_three:
        concentration = next((row for row in rows[1:] if "浓度" in _clean(row[0])), [])
        peak_area = next((row for row in rows[1:] if "峰面积" in _clean(row[0])), [])
        for column in range(1, len(rows[0])):
            result["linearity"].append(_record({"solutionName": _clean(rows[0][column]),
                "field2": _clean(concentration[column] if len(concentration) > column else ""),
                "peakArea": _clean(peak_area[column] if len(peak_area) > column else "")}, evidence))
        return True

    if "量取体积" in header and "定容" in header and "溶液" in header and "名称" in header:
        for row in rows[1:]:
            if not any(row):
                continue
            name = _clean(row[-1])
            values = {f"field{index + 1}": _clean(value) for index, value in enumerate(row[:-1])}
            result["linearityPreparation"].append(_record({**values, "solutionName": name}, evidence))
        return True

    if profile_enabled("SYSTEM_SUITABILITY_MATRIX") and (header.startswith("No.|") or header.startswith("No|")) and "保留时间" in first_three and "峰面积" in first_three and "浓度" not in first_three:
        subheader = rows[1] if len(rows) > 1 else []
        impurities = rows[0]
        for row in rows[2:]:
            sequence = _at(row, 0)
            if not _is_system_suitability_detail(sequence):
                continue
            column = 1
            while column + 1 < len(row):
                impurity = _at(impurities, column)
                retention = _at(row, column)
                peak_area = _at(row, column + 1)
                if impurity and (retention or peak_area):
                    result["systemSuitability"].append(_record({
                        "sequence": f"{impurity}-{sequence}" if impurity else sequence,
                        "injectionId": sequence, "impurityName": impurity,
                        "retentionTime": retention, "peakArea": peak_area,
                    }, evidence))
                column += 2
        return True

    if profile_enabled("SPECIFICITY_RESULT_TABLE") and "杂质名称" in header and "溶液名称" in header and "保留时间" in header and "峰面积" in header:
        current_impurity = ""
        for row in rows[1:]:
            current_impurity = _clean(row[0]) or current_impurity
            if len(row) > 1 and _clean(row[1]):
                result["specificity"].append(_record({"impurityName": current_impurity,
                    "solutionName": _clean(row[1]), "retentionTime": _at(row, 2),
                    "peakArea": _at(row, 3)}, evidence))
        return True

    if "人员/日期" in header and "No." in header and "峰面积" in header:
        target = "intermediatePrecision" if "中间精密度" in instance.get("title", "") else "repeatability"
        current_person = ""
        for row in rows[1:]:
            current_person = _clean(row[0]) or current_person
            result[target].append(_record({"field1": current_person, "sequence": _at(row, 1),
                "field3": _at(row, 2), "retentionTime": _at(row, 3), "peakArea": _at(row, 4),
                "field6": _at(row, 5), "field7": _at(row, 6)}, evidence))
        return True

    if ("No." in header or header.startswith("No|")) and "保留时间" in header and "峰面积" in header and "浓度" in header:
        target = "intermediatePrecision" if "中间精密度" in instance.get("title", "") else "repeatability"
        for row in rows[1:]:
            result[target].append(_record({"sequence": _clean(row[0]), "field2": _at(row, 1),
                "retentionTime": _at(row, 2), "peakArea": _at(row, 3),
                "field5": _at(row, 4), "field6": _at(row, 5)}, evidence))
        return True

    if "杂质名称" in header and "平均含量" in header:
        impurity = ""
        for row in rows[1:]:
            impurity = _clean(row[0]) or impurity
            result["blankAmount"].append(_record({"impurityName": impurity, "sequence": _at(row, 1),
                "field3": _at(row, 2), "peakArea": _at(row, 3), "field5": _at(row, 4),
                "content": _at(row, 5), "field7": _at(row, 6)}, evidence))
        return True

    if ("回收率" in header and "加入量" in header) or ("溶液" in header and "回收率" in header and "平均值" in header):
        solution = ""
        for row in rows[1:]:
            solution = _clean(row[0]) or solution
            result["accuracy"].append(_record({"solutionName": solution, "sequence": _at(row, 1),
                "field3": _at(row, 2), "field4": _at(row, 3), "field5": _at(row, 4),
                "field6": _at(row, 5), "field7": _at(row, 6), "field8": _at(row, 7),
                "field9": _at(row, 8)}, evidence))
        return True

    if "时间" in header and ("对照品溶液" in header or "100%加标" in header):
        for row in rows[2 if len(rows) > 1 and "浓度" in "|".join(rows[1]) else 1:]:
            result["solutionStability"].append(_record({"timePoint": _clean(row[0]),
                "field2": _at(row, 1), "field3": _at(row, 2), "field4": _at(row, 3),
                "field5": _at(row, 4)}, evidence))
        return True

    if profile_enabled("ROBUSTNESS_SPECIFICITY_TABLE") and "溶液名称" in header and "色谱柱1" in header and "色谱柱2" in header:
        for row in rows[1:]:
            result["robustnessSpecificity"].append(_record({"solutionName": _clean(row[0]),
                "field2": _at(row, 1), "field3": _at(row, 2)}, evidence))
        return True

    if profile_enabled("ROBUSTNESS_SEQUENCE_TABLE") and "溶液" in header and "进样针数" in header and "接受标准" in header:
        for row in rows[1:]:
            result["robustnessSequence"].append(_record({"field1": _clean(row[0]),
                "field2": _at(row, 1), "acceptanceCriteria": _at(row, 2)}, evidence))
        return True

    if ("溶液|结果" in header or "溶液|结论" in header) and "实验设计" not in path:
        for row in rows[1:]:
            result["robustnessResult"].append(_record({"field1": _clean(row[0]),
                                                        "field2": _at(row, 1)}, evidence))
        return True

    if "实验设计" in path and "溶液" in header and "接受标准" in header:
        for row in rows[1:]:
            if _at(row, 0) and _at(row, 1):
                result["validationSummary"].append(_record({"field1": _at(row, 0),
                    "validationItemCode": validation_code(_at(row, 0), True),
                    "acceptanceCriteria": _at(row, 1), "conclusion": ""}, evidence))
        return True

    if ("序号" in header and "名称" in header and "批号" in header) or header.startswith("批次|"):
        if header.startswith("批次|"):
            batches = rows[0][1:]
            concentration = rows[1][1:] if len(rows) > 1 else []
            for impurity_row in rows[2:]:
                for index, batch in enumerate(batches):
                    result["sampleResults"].append(_record({"name": _clean(impurity_row[0]),
                        "batchNo": _clean(batch), "field3": _clean(concentration[index] if index < len(concentration) else ""),
                        "peakArea": "", "field5": "", "content": _at(impurity_row, index + 1)}, evidence))
        else:
            for row in rows[1:]:
                result["sampleResults"].append(_record({"name": _at(row, 1), "batchNo": _at(row, 2),
                    "field3": _at(row, 3), "peakArea": _at(row, 4), "field5": "",
                    "content": _at(row, 5)}, evidence))
        return True

    return False


def normalize_instance(instance: dict[str, Any], fields: list[dict[str, Any]] | None = None,
                       extraction_rules: list[dict[str, Any]] | None = None,
                       groups: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    collections: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name in ("samples", "referenceStandards", "instruments", "columns", "reagents", "weighings"):
        for source_item in instance.get(name, []):
            item = dict(source_item)
            evidence = dict(item.get("evidence") or {})
            evidence.update({"instanceId": instance["instanceId"],
                             "instanceTitle": instance.get("title", "")})
            item["evidence"] = evidence
            collections[name].append(item)

    parser_profiles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rule in extraction_rules or []:
        config = rule.get("config") or {}
        if not isinstance(config, dict) or config.get("parser") != "HTML_TABLE_GRID":
            continue
        profile = str(config.get("parserProfile") or "")
        if not profile:
            continue
        parser_profiles[profile].append(rule)

    unmatched = []
    for rich_text in instance.get("richTexts", []):
        raw_html = rich_text.get("html", "")
        try:
            root = html.fragment_fromstring(raw_html, create_parent="div")
        except (ValueError, TypeError):
            root = None
        tables = root.xpath(".//table") if root is not None else []
        for index, table in enumerate(tables, start=1):
            rows = _table_grid(table)
            evidence = _evidence(instance, rich_text, index, rows[0] if rows else [])
            configured_targets = apply_configured_group_tables(
                rows, ">".join(rich_text.get("sectionPath", [])), groups or [], evidence, collections,
            )
            standard_mapping_matched = any(target in COLLECTION_ORDER for target in configured_targets)
            if not standard_mapping_matched and not _classify_table(
                instance, rich_text, index, rows, collections, parser_profiles,
            ):
                unmatched.append({
                    "instanceId": instance["instanceId"], "instanceTitle": instance.get("title", ""),
                    "sectionPath": rich_text.get("sectionPath", []), "richTextId": rich_text.get("id"),
                    "tableIndex": index, "headers": rows[0] if rows else [], "rows": rows,
                    "plainText": rich_text.get("plainText", ""), "evidence": rich_text.get("evidence", {}),
                })
        path = ">".join(rich_text.get("sectionPath", []))
        plain = _clean(rich_text.get("plainText", ""))
        if not tables and plain:
            evidence = _evidence(instance, rich_text, 0, [])
            if "计算公式" in path:
                collections["formulas"].append(_record({"text": plain}, evidence))
            elif "实验结论" in path:
                project = next((item for item in reversed(rich_text.get("sectionPath", []))
                                if item and item not in {"实验结论", "实验结果"}), instance.get("title", ""))
                collections["conclusions"].append(_record({
                    "text": plain, "validationProject": project,
                    "validationCode": validation_code(project),
                }, evidence))

    result = {
        "project": instance.get("project", {}), "document": instance.get("document", {}),
        "approval": instance.get("approval", []), "instances": [{
            "instanceId": instance["instanceId"], "title": instance.get("title", ""),
            "projectId": instance.get("projectId"), "version": instance.get("version"),
        }],
        **{name: collections.get(name, []) for name in COLLECTION_ORDER},
        "unmatched": unmatched,
    }
    for group in groups or []:
        payload_key = str(group.get("groupCode") or "").strip()
        if payload_key and payload_key not in result:
            result[payload_key] = collections.get(payload_key, [])
    result["lodConclusion"] = next((item.get("conclusion", "") for item in result["jiancexian"]
                                    if item.get("conclusion")), "")
    if fields and extraction_rules:
        apply_configured_extraction(instance, result, fields, extraction_rules)
    _add_solution_views(result)
    return result


def _add_solution_views(payload: dict[str, Any]) -> None:
    for target, code in SOLUTION_VIEW_CODES.items():
        payload[target] = [item for item in payload.get("solutions", [])
                           if item.get("validationCode") == code]
    payload["intermediateLinearityPreparation"] = [
        item for item in payload.get("linearityPreparation", [])
        if "中间精密度" in item.get("evidence", {}).get("instanceTitle", "")
    ]
    payload["intermediateLinearity"] = [
        item for item in payload.get("linearity", [])
        if "中间精密度" in item.get("evidence", {}).get("instanceTitle", "")
    ]


def merge_instances(instances: list[dict[str, Any]], resolutions: dict[str, str] | None = None,
                    fields: list[dict[str, Any]] | None = None,
                    extraction_rules: list[dict[str, Any]] | None = None,
                    groups: list[dict[str, Any]] | None = None,
                    normalized: bool = False) -> dict[str, Any]:
    from .lims_merge import merge_instances as _merge_instances

    return _merge_instances(instances, resolutions, fields, extraction_rules, groups, normalized)
