from typing import Any

from fastapi import HTTPException


def manual_edit_locked() -> HTTPException:
    return HTTPException(409, {"code": "MANUAL_EDIT_LOCKED", "message": "Word 已人工编辑并保存，不能再次自动生成；请新建报告。"})


def default_report_data() -> dict[str, Any]:
    return {
        "report_no": "", "customer": "", "sample": "", "project_name": "", "report_date": "",
        "conclusion": "", "author": "", "reviewer": "", "approver": "", "template_version": "V1.0",
        "test_items": [], "field_sources": {}, "original_values": {}, "source_payloads": {},
    }


def resolved_report_title(title: str | None, data: dict[str, Any]) -> str:
    explicit = str(title or "").strip()
    if explicit and explicit != "未命名报告":
        return explicit
    if project_name := str(data.get("project_name") or "").strip():
        return project_name
    if sample := str(data.get("sample") or "").strip():
        return f"{sample}分析报告"
    return str(data.get("report_no") or "").strip() or "未命名报告"


def has_custom_report_title(item: dict[str, Any]) -> bool:
    title, data = str(item.get("title") or "").strip(), item.get("resolved_data") or {}
    automatic = {"", "未命名报告", str(data.get("project_name") or "").strip(),
                 str(data.get("report_no") or "").strip()}
    if sample := str(data.get("sample") or "").strip():
        automatic.add(f"{sample}分析报告")
    return title not in automatic


def flatten_values(data: dict[str, Any]) -> dict[str, str]:
    values = {key: str(data.get(key) or "") for key in (
        "report_no", "customer", "sample", "project_name", "report_date",
        "conclusion", "author", "reviewer", "approver",
    )}
    for item in data.get("test_items", []):
        for field in ("category", "name", "method", "requirement", "result", "unit", "conclusion"):
            values[f"testItems[id={item['id']}].{field}"] = str(item.get(field) or "")
    return values


def binding_label(field_code: str) -> str:
    labels = {
        "report_no": "报告编号", "customer": "客户名称", "sample": "样品名称",
        "project_name": "项目名称", "report_date": "报告日期", "conclusion": "报告结论",
        "author": "编制人", "reviewer": "复核人", "approver": "批准人",
    }
    if field_code in labels:
        return labels[field_code]
    field = field_code.rsplit(".", 1)[-1]
    return {"category": "分类", "name": "检测项目", "method": "检测方法",
            "requirement": "技术要求", "result": "检测结果", "unit": "单位",
            "conclusion": "结论"}.get(field, field)
