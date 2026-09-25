"""将可审阅的字段目录/Excel 规则清单安装到现有标准编组。"""

import json
from pathlib import Path
from typing import Any

from .system_field_group_levels import (
    delete_group_level, field_path_for, json_path_for, move_field_to_level, save_group_level,
)
from .system_field_groups import (
    assign_field_to_group, list_system_field_groups, remove_field_from_group, sync_group_field_paths,
)


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
    levels = list(group.get("levels", [])) + list(manifest.get("levels", []))
    levels = list({level["levelKey"]: level for level in levels}.values())
    kinds = {level["levelKey"]: level["kind"] for level in levels}
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
        relative = field_path_for(level, kinds.get(level, ""), key, levels)
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
    levels = manifest.get("levels")
    if levels is not None:
        if not isinstance(levels, list):
            raise ValueError("Excel 字段目录的 levels 必须是数组")
        for level in levels:
            if not isinstance(level, dict):
                raise ValueError("Excel 字段目录的层级配置必须是对象")
    existing = {field["fieldCode"]: field for field in group["fields"]}
    retired = manifest.get("retireFields", [])
    if not isinstance(retired, list) or any(not isinstance(code, str) for code in retired):
        raise ValueError("退役字段配置必须是字段编码数组")
    if len(retired) != len(set(retired)) or set(retired) & {spec["fieldCode"] for spec in prepared}:
        raise ValueError("退役字段不能重复或同时出现在新字段清单中")
    retired_levels = manifest.get("retireLevels", [])
    if not isinstance(retired_levels, list) or any(not isinstance(key, str) for key in retired_levels):
        raise ValueError("退役层级配置必须是层键名数组")
    if len(retired_levels) != len(set(retired_levels)):
        raise ValueError("退役层级不能重复")
    levels_by_key = {level["levelKey"]: level for level in group["levels"]}
    for position, key in enumerate(retired_levels):
        if key not in levels_by_key:
            raise ValueError(f"退役层 {key} 不存在")
        children = [level["levelKey"] for level in group["levels"]
                    if level.get("parentLevelKey") == key]
        if any(child not in retired_levels[:position] for child in children):
            raise ValueError(f"退役层 {key} 的子层必须先退役")
        if any(field["levelKey"] == key and field["fieldCode"] not in retired
               for field in group["fields"]):
            raise ValueError(f"退役层 {key} 仍包含未退役字段")
    for code in retired:
        field = database.get_lims_field(code)
        if field is None or (code not in existing and field["enabled"]):
            raise ValueError(f"退役字段 {code} 不属于目标编组或不存在")
    for spec in prepared:
        code = spec["fieldCode"]
        field = database.get_lims_field(code)
        if field and code not in existing:
            raise ValueError(f"字段 {code} 已属于其他编组，不能自动转移")
        if code in existing and field and field["cardinality"] != "MANY":
            raise ValueError(f"字段 {code} 的数据库基数不是 MANY，请先在字段目录核实")
        if code in existing and existing[code].get("levelKey", "") != spec["levelKey"]:
            raise ValueError(f"字段 {code} 的数据库层级与清单不一致，请先在字段目录核实")
        rules = [rule for rule in database.list_system_field_rules(code)
                 if rule["sourceType"] == "EXCEL"]
        if len(rules) > 1:
            raise ValueError(f"字段 {code} 存在多条 Excel 规则，无法确定要更新哪一条")
    added_rules: list[str] = []
    for level in levels or []:
        save_group_level(database, group["groupCode"], level)
    for spec in prepared:
        code = spec["fieldCode"]
        if code not in existing:
            database.upsert_lims_field({
                "fieldCode": code, "label": spec["label"], "groupCode": group["label"],
                "collectionCode": group["groupCode"], "dataType": "string",
                "cardinality": "MANY", "jsonKey": spec["jsonKey"],
                "legacyJsonPath": spec["legacyJsonPath"], "enabled": True,
            })
            assign_field_to_group(database, group["groupCode"], code)
            if spec["levelKey"]:
                move_field_to_level(database, group["groupCode"], code, spec["levelKey"])
        rules = [rule for rule in database.list_system_field_rules(code)
                 if rule["sourceType"] == "EXCEL"]
        if rules:
            continue
        database.save_system_field_rule({
            "fieldCode": code, "name": spec["label"], "sourceType": "EXCEL",
            "priority": 50, "config": spec["config"], "enabled": True,
        })
        added_rules.append(code)
    if levels:
        sync_group_field_paths(database, group["groupCode"])
    for code in retired:
        field = database.get_lims_field(code)
        if code in existing:
            remove_field_from_group(database, group["groupCode"], code)
        if field["enabled"]:
            database.upsert_lims_field({**field, "enabled": False})
    for key in retired_levels:
        delete_group_level(database, group["groupCode"], key)
    return added_rules
