from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from .auth import AuthManager
from .config import Settings
from .database import Database
from .report_utils import manual_edit_locked, resolved_report_title
from .schemas import ApplyLimsRequest, ReportTask
from .services.report_lims_refresh import (
    LIMS_SOURCE_KEY,
    LimsConflictError,
    LimsSourceError,
    lims_source_metadata,
    record_lims_field_provenance,
    recognition_metadata,
    require_latest_lims,
)
from .services.payload_paths import first_payload_value


def _standard_value(
    payload: dict[str, Any], fields: list[dict[str, Any]], collection: str, json_key: str,
) -> Any:
    matches = [
        field for field in fields
        if field.get("enabled", True)
        and field.get("collectionCode") == collection
        and field.get("jsonKey") == json_key
    ]
    if len(matches) != 1:
        raise ValueError(f"标准字段目录中 {collection}.{json_key} 必须且只能配置一次")
    return first_payload_value(payload, str(matches[0].get("legacyJsonPath") or ""))


def create_report_lims_router(
    database: Database, settings: Settings, auth: AuthManager,
    required_owned_report: Callable[[str, dict[str, Any]], dict[str, Any]],
    report_response: Callable[[dict[str, Any]], ReportTask],
    render_report_word: Callable[..., str],
) -> APIRouter:
    router = APIRouter()

    @router.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims-legacy", response_model=ReportTask,
                 include_in_schema=False)
    def apply_lims_to_report(report_id: str, request: ApplyLimsRequest) -> ReportTask:
        raise HTTPException(410, "旧版 LIMS 接口已停用")

    @router.post(f"{settings.api_prefix}/reports/{{report_id}}/apply-lims", response_model=ReportTask)
    def apply_lims_instances_to_report(
        report_id: str, request: ApplyLimsRequest,
        user: dict = Depends(auth.require("REPORT_EDIT")),
    ) -> ReportTask:
        item = required_owned_report(report_id, user)
        if item.get("word_edit_locked") and not request.force:
            raise manual_edit_locked()
        try:
            recognition = require_latest_lims(
                database, settings, request.project_id, request.instance_ids, request.conflict_resolutions,
            )
            payload = recognition["payload"]
            fields = database.list_lims_fields(True)
            sample_name = _standard_value(payload, fields, "samples", "sampleName")
            client_name = _standard_value(payload, fields, "samples", "clientName")
        except LimsConflictError as error:
            raise HTTPException(409, {
                "message": str(error), "conflicts": error.conflicts,
            }) from error
        except LimsSourceError as error:
            status_code = 404 if "不存在" in str(error) else 422
            raise HTTPException(status_code, str(error)) from error
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            raise HTTPException(422, f"LIMS 数据读取失败：{error}") from error

        data = dict(item["resolved_data"])
        sample = payload.get("samples", [{}])[0] if payload.get("samples") else {}
        first_instance = payload["instances"][0]
        values = {
            "report_no": payload.get("document", {}).get("code") or "+".join(request.instance_ids),
            "project_name": payload.get("project", {}).get("name") or first_instance.get("title", ""),
            "sample": sample_name or "",
            "customer": client_name or "",
            "author": first_instance.get("createdBy", "") or "",
            "template_version": payload.get("document", {}).get("version") or data.get("template_version", "V1.0"),
        }
        sources = dict(data.get("field_sources", {}))
        originals = dict(data.get("original_values", {}))
        for code, value in values.items():
            if value in (None, ""):
                continue
            old_value = str(data.get(code) or "")
            value = str(value)
            data[code] = value
            sources[code] = {"type": "LIMS", "record_id": sample.get("sourceRecordId") or request.instance_ids[0]}
            originals[code] = value
            if old_value != value:
                database.add_change(report_id, code, old_value, value, user["display_name"], "载入 LIMS 数据")
        data["field_sources"] = sources
        data["original_values"] = originals
        source_payloads = dict(data.get("source_payloads", {}))
        source_payloads["LIMS"] = payload
        source_payloads["LIMS_RECOGNITION"] = recognition_metadata(recognition)
        source_payloads[LIMS_SOURCE_KEY] = lims_source_metadata(
            request.project_id, request.instance_ids, request.conflict_resolutions,
        )
        data["source_payloads"] = source_payloads
        record_lims_field_provenance(
            data, payload, fields, "+".join(request.instance_ids),
        )
        try:
            output_name = render_report_word(item, data, payload,
                                             phase="载入 LIMS 实验记录", actor=user["id"])
        except Exception as error:
            raise HTTPException(500, f"LIMS 数据填充 Word 失败：{error}") from error
        updated = database.update_report(
            report_id, title=resolved_report_title(item.get("title"), data), resolved_data=data,
            status="EDITING", output_name=output_name, updated_by=user["id"],
            word_edit_locked=0, word_edited_at=None,
        )
        database.create_version(report_id, data, f"载入 LIMS 实验记录 {', '.join(request.instance_ids)}")
        return report_response(updated)

    return router
