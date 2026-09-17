from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from .auth import AuthManager
from .config import Settings
from .database import Database
from .report_utils import manual_edit_locked, resolved_report_title
from .schemas import ApplyLimsRequest, ReportTask
from .services.lims_normalizer import merge_instances
from .services.system_field_group_assembler import apply_group_contracts
from .services.system_field_groups import list_system_field_groups


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
        imported = database.get_lims_import(request.import_id)
        if not imported:
            raise HTTPException(404, "LIMS 导入记录不存在")
        try:
            groups = list_system_field_groups(database)
            instances = []
            for instance_id in request.instance_ids:
                payload = database.get_lims_normalized_payload(request.import_id, instance_id)
                if payload is None:
                    raise KeyError(instance_id)
                instances.append(payload)
            recognition = merge_instances(
                instances, request.conflict_resolutions,
                fields=database.list_lims_fields(True), groups=groups, normalized=True,
            )
            if recognition["unresolvedConflictCount"]:
                raise HTTPException(409, {
                    "message": "存在未处理的 LIMS 数据冲突",
                    "conflicts": recognition["conflicts"],
                })
            payload = recognition["payload"]
            apply_group_contracts(payload, groups)
        except KeyError as error:
            raise HTTPException(404, f"LIMS 实验记录不存在：{error.args[0]}") from error
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            raise HTTPException(422, f"LIMS 数据读取失败：{error}") from error

        data = dict(item["resolved_data"])
        sample = payload.get("samples", [{}])[0] if payload.get("samples") else {}
        first_instance = instances[0]
        values = {
            "report_no": payload.get("document", {}).get("code") or "+".join(request.instance_ids),
            "project_name": payload.get("project", {}).get("name") or first_instance.get("title", ""),
            "sample": sample.get("sampleName", ""),
            "customer": sample.get("clientName", ""),
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
        source_payloads["LIMS_RECOGNITION"] = {
            "recognizedCounts": recognition["recognizedCounts"],
            "duplicateCount": recognition["duplicateCount"],
            "unmatched": recognition["unmatched"],
            "instances": payload["instances"],
        }
        data["source_payloads"] = source_payloads
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
