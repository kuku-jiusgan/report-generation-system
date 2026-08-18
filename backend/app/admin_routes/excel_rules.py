from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import Settings
from ..database import Database
from ..services.excel_rule_engine import ExcelRuleError, execute_excel_rules, validate_excel_snapshot


def register_excel_rule_routes(router: APIRouter, database: Database, settings: Settings) -> None:
    @router.get("/excel-rules")
    def get_excel_rules() -> dict[str, Any]:
        return {"draft": database.excel_rule_draft(), "published": database.active_excel_rules(),
                "versions": database.excel_rule_versions()}

    @router.put("/excel-rules/draft")
    def save_excel_rule_draft(item: dict[str, Any]) -> dict[str, Any]:
        snapshot = item.get("snapshot") if isinstance(item.get("snapshot"), dict) else item
        errors = validate_excel_snapshot(snapshot)
        if errors:
            raise HTTPException(422, errors)
        return database.save_excel_rule_draft(snapshot)

    @router.post("/excel-rules/draft/test")
    def test_excel_rule_draft(item: dict[str, Any]) -> dict[str, Any]:
        draft = database.excel_rule_draft()
        if not draft:
            raise HTTPException(404, "请先保存 Excel 规则草稿")
        source = database.get_source(str(item.get("sourceId") or ""))
        if not source or source.get("source_type") != "EXCEL":
            raise HTTPException(422, "请选择已上传的 Excel 样例")
        path = settings.uploads_dir / source["stored_name"]
        try:
            payload = execute_excel_rules(path, draft["snapshot"], draft["id"])
            report = {"valid": True, "sourceId": source["id"], "warnings": payload["_meta"]["warnings"],
                      "collections": {key: len(value) if isinstance(value, list) else 1
                                      for key, value in payload.items() if key != "_meta"}, "payload": payload}
        except (ExcelRuleError, KeyError, TypeError, ValueError) as error:
            report = {"valid": False, "sourceId": source["id"], "errors": [str(error)]}
        database.record_excel_rule_validation(draft["id"], report)
        return report

    @router.post("/excel-rules/draft/publish")
    def publish_excel_rule_draft() -> dict[str, Any]:
        draft = database.excel_rule_draft()
        if not draft:
            raise HTTPException(404, "没有待发布的 Excel 规则草稿")
        try:
            return database.publish_excel_rule_draft(draft["id"])
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
