"""将可审阅的字段目录/Excel 规则清单安装到现有标准编组。"""

import json
from pathlib import Path
from typing import Any

from .system_field_group_levels import field_path_for, json_path_for
from .system_field_groups import assign_field_to_group, list_system_field_groups, sync_group_field_paths
from .system_field_group_levels import move_field_to_level


def read_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("fields"), list):
        raise ValueError("Excel 字段目录清单必须包含 fields 数组")
    codes = [str(item.get("code") or "") for item in manifest["fields"]]
    if not codes or any(not code for code in codes) or len(codes) != len(set(codes)):
        raise ValueError("Excel 字段目录清单含空编码或重复编码")
    if not isinstance(manifest.get("defaults"), dict):
        raise ValueError("Excel 字段目录清单缺少默认规则配置")
    return manifest


def prepared_fields(manifest: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
    if group.get("groupCode") != manifest.get("groupCode") or group.get("cardinality") != "MANY":
        raise ValueError("目标编组不存在或不是多行编组")
    kinds = {level["levelKey"]: level["kind"] for level in group.get("levels", [])}
    existing = {field["fieldCode"]: field for field in group.get("fields", [])}
    result = []
    for spec in manifest["fields"]:
        if not isinstance(spec, dict) or not isinstance(spec.get("config"), dict):
            raise ValueError("Excel 字段必须包含字段编码及配置")
        code, level = str(spec["code"]), str(spec.get("level") or "")
        if level and level not in kinds:
            raise ValueError(f"字段 {code} 所需层 {level} 不存在")
        if code in existing and spec.get("label") and spec["label"] != existing[code]["label"]:
            raise ValueError(f"已有字段 {code} 的名称不一致，请先核实目录")
        if code not in existing and not str(spec.get("label") or "").strip():
            raise ValueError(f"新字段 {code} 必须配置名称")
        key = str(existing.get(code, {}).get("jsonKey") or code.rsplit(".", 1)[-1])
        relative = field_path_for(level, kinds.get(level, ""), key)
        path = json_path_for(f"$.{group['groupCode']}", "MANY", relative)
        config = {**manifest["defaults"], **spec["config"], "sourcePath": path}
        result.append({"fieldCode": code, "label": spec.get("label") or existing[code]["label"],
                       "levelKey": level, "jsonKey": key, "legacyJsonPath": path,
                       "config": config})
    return result


def apply_manifest(database: Any, manifest: dict[str, Any]) -> list[str]:
    group = next((item for item in list_system_field_groups(database)
                  if item["groupCode"] == manifest.get("groupCode")), None)
    if group is None:
        raise ValueError("Excel 字段目录清单指定的编组不存在")
    prepared = prepared_fields(manifest, group)
    existing = {field["fieldCode"]: field for field in group["fields"]}
    for spec in prepared:
        code = spec["fieldCode"]
        field = database.get_lims_field(code)
        if field and code not in existing:
            raise ValueError(f"字段 {code} 已属于其他编组，不能自动转移")
        rules = [rule for rule in database.list_system_field_rules(code)
                 if rule["sourceType"] == "EXCEL"]
        if rules and (len(rules) != 1 or rules[0]["config"] != spec["config"]):
            raise ValueError(f"字段 {code} 已有不同的 Excel 规则，请先在管理界面核实")
    for spec in prepared:
        code = spec["fieldCode"]
        current = database.get_lims_field(code)
        if code not in existing:
            database.upsert_lims_field({
                "fieldCode": code, "label": spec["label"], "groupCode": group["label"],
                "collectionCode": group["groupCode"], "dataType": "string",
                "cardinality": "MANY", "jsonKey": spec["jsonKey"],
                "legacyJsonPath": spec["legacyJsonPath"], "enabled": True,
            })
            assign_field_to_group(database, group["groupCode"], code)
        elif current["cardinality"] != "MANY":
            database.upsert_lims_field({**current, "cardinality": "MANY"})
        if existing.get(code, {}).get("levelKey", "") != spec["levelKey"]:
            move_field_to_level(database, group["groupCode"], code, spec["levelKey"])
    sync_group_field_paths(database, group["groupCode"])
    for spec in prepared:
        code = spec["fieldCode"]
        rules = [rule for rule in database.list_system_field_rules(code)
                 if rule["sourceType"] == "EXCEL"]
        if not rules:
            database.save_system_field_rule({
                "fieldCode": code, "name": spec["label"], "sourceType": "EXCEL",
                "priority": 50, "config": spec["config"], "enabled": True,
            })
    return [spec["fieldCode"] for spec in prepared]
