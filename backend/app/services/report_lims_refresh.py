import logging
from typing import Any

from .lims_normalizer import merge_instances, normalize_instance
from .lims_oracle import query_lims_project
from .payload_paths import read_payload_path
from .system_field_group_assembler import apply_group_contracts
from .system_field_groups import list_system_field_groups
from .system_field_rule_invariant import rules_by_field


logger = logging.getLogger(__name__)
LIMS_SOURCE_KEY = "LIMS_SOURCE"


class LimsSourceError(ValueError):
    pass


class LimsConflictError(LimsSourceError):
    def __init__(self, conflicts: list[dict[str, Any]]):
        super().__init__("存在未处理的 LIMS 数据冲突")
        self.conflicts = conflicts


def record_lims_field_provenance(
    report_data: dict[str, Any], payload: dict[str, Any], fields: list[dict[str, Any]],
    record_id: str,
) -> None:
    """只登记 LIMS 本次实际提供的标准字段，不覆盖其他来源独有字段。"""
    sources = report_data.setdefault("field_sources", {})
    originals = report_data.setdefault("original_values", {})
    enabled_fields = [field for field in fields if field.get("enabled", True)]
    field_codes = {str(field.get("fieldCode") or "") for field in enabled_fields}
    for code in field_codes:
        if str((sources.get(code) or {}).get("type") or "").upper() == "LIMS":
            sources.pop(code, None)
            originals.pop(code, None)
    for field in enabled_fields:
        code = str(field.get("fieldCode") or "")
        path = str(field.get("legacyJsonPath") or code)
        value = read_payload_path(payload, path)
        if value in (None, "", [], {}):
            continue
        sources[code] = {
            "type": "LIMS", "record_id": record_id, "sourcePath": path,
        }
        originals[code] = value


def lims_source_metadata(
    project_id: str, instance_ids: list[str], conflict_resolutions: dict[str, str],
) -> dict[str, Any]:
    return {
        "projectId": project_id,
        "instanceIds": list(instance_ids),
        "conflictResolutions": dict(conflict_resolutions),
    }


def _recognize_instances(
    database: Any, instances: list[dict[str, Any]],
    conflict_resolutions: dict[str, str] | None,
) -> dict[str, Any]:
    fields = database.list_lims_fields(True)
    rules = database.list_lims_extraction_rules()
    rules_by_field(rules)
    groups = list_system_field_groups(database)
    normalized = [
        apply_group_contracts(normalize_instance(raw, fields, rules, groups), groups)
        for raw in instances
    ]
    return merge_instances(
        normalized, conflict_resolutions, fields=fields,
        extraction_rules=rules, groups=groups, normalized=True,
    )


def recognize_imported_lims(
    database: Any, import_id: str, instance_ids: list[str],
    conflict_resolutions: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not database.get_lims_import(import_id):
        raise LimsSourceError("LIMS 导入记录不存在")
    instances = []
    for instance_id in instance_ids:
        raw = database.get_lims_instance_payload(import_id, instance_id)
        if raw is None:
            raise LimsSourceError(f"LIMS 实验记录不存在：{instance_id}")
        instances.append(raw)
    logger.info("识别 LIMS 查询预览 import_id=%s instances=%d", import_id, len(instances))
    return _recognize_instances(database, instances, conflict_resolutions)


def recognize_latest_lims(
    database: Any, settings: Any, project_id: str, instance_ids: list[str],
    conflict_resolutions: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        _, instances = query_lims_project(settings, project_id)
    except Exception as error:
        logger.exception("实时查询 LIMS 失败 project_id=%s", project_id)
        raise LimsSourceError(f"实时查询 LIMS 项目 {project_id} 失败：{error}") from error
    by_id = {str(item.get("instanceId") or ""): item for item in instances}
    missing = [instance_id for instance_id in instance_ids if instance_id not in by_id]
    if missing:
        raise LimsSourceError(f"LIMS 项目 {project_id} 中已不存在实验记录：{', '.join(missing)}")
    selected = [by_id[instance_id] for instance_id in instance_ids]
    logger.info("使用 LIMS 实时数据 project_id=%s instances=%d", project_id, len(selected))
    return _recognize_instances(database, selected, conflict_resolutions)


def require_latest_lims(
    database: Any, settings: Any, project_id: str, instance_ids: list[str],
    conflict_resolutions: dict[str, str],
) -> dict[str, Any]:
    recognition = recognize_latest_lims(
        database, settings, project_id, instance_ids, conflict_resolutions,
    )
    if recognition["unresolvedConflictCount"]:
        raise LimsConflictError(recognition["conflicts"])
    apply_group_contracts(recognition["payload"], list_system_field_groups(database))
    return recognition


def refresh_report_lims_payload(
    database: Any, settings: Any, report_data: dict[str, Any],
) -> dict[str, Any]:
    payloads = report_data.get("source_payloads")
    if not isinstance(payloads, dict):
        raise LimsSourceError("报告数据源载荷格式无效")
    source = payloads.get(LIMS_SOURCE_KEY)
    if not isinstance(source, dict):
        raise LimsSourceError("旧报告未保存 LIMS 项目绑定，请重新载入 LIMS 实验记录后再重新生成")
    project_id = str(source.get("projectId") or "").strip()
    instance_ids = source.get("instanceIds")
    resolutions = source.get("conflictResolutions", {})
    if not project_id or not isinstance(instance_ids, list) or not instance_ids:
        raise LimsSourceError("报告保存的 LIMS 来源信息不完整，请重新载入 LIMS 实验记录")
    if not isinstance(resolutions, dict):
        raise LimsSourceError("报告保存的 LIMS 冲突选择格式无效，请重新载入 LIMS 实验记录")
    recognition = require_latest_lims(
        database, settings, project_id, [str(value) for value in instance_ids],
        {str(key): str(value) for key, value in resolutions.items()},
    )
    updated_payloads = dict(payloads)
    updated_payloads["LIMS"] = recognition["payload"]
    updated_payloads["LIMS_RECOGNITION"] = recognition_metadata(recognition)
    report_data["source_payloads"] = updated_payloads
    record_lims_field_provenance(
        report_data, recognition["payload"], database.list_lims_fields(True),
        "+".join(str(value) for value in instance_ids),
    )
    return recognition


def recognition_metadata(recognition: dict[str, Any]) -> dict[str, Any]:
    payload = recognition["payload"]
    return {
        "recognizedCounts": recognition["recognizedCounts"],
        "duplicateCount": recognition["duplicateCount"],
        "unmatched": recognition["unmatched"],
        "instances": payload["instances"],
    }
