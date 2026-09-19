import hashlib
import json
from pathlib import Path

from .template_compiler import compile_template


def _compile_failure_message(report: dict) -> str:
    """把编译错误摊开写进异常，光说"N 个错误"排查时等于没说。"""
    errors = report.get("errors", [])
    details = "；".join(
        f"{item.get('locationId') or item.get('controlTag') or item.get('code')}"
        f"（{item.get('fieldCode') or item.get('code')}）：{item.get('message', '')}"
        for item in errors[:5]
    )
    more = f"，另有 {len(errors) - 5} 个错误" if len(errors) > 5 else ""
    return (f"运行时模板编译失败：{len(errors)} 个错误。{details}{more}。"
            f"请在模板设计器中修正这些字段的 Word 位置，或停用不再使用的映射。")


def resolve_runtime_template(
    settings, rule_admin, apply_content_block_rules,
    template_id: str | None = None, template_version_id: str | None = None,
) -> tuple[Path, list[dict], list[dict], dict[str, str]]:
    active = rule_admin.active_runtime_template(template_id, template_version_id)
    if active:
        snapshot = active["snapshot"]
        # 表格布局是设计器的当前配置；重新生成不能继续使用发布快照中的旧布局。
        if not template_id:
            snapshot = {**snapshot, "tableRules": rule_admin.list_table_rules()}
        published_template = active.get("templateFile")
    else:
        snapshot, published_template = rule_admin.active_runtime_rules()
        snapshot = {**snapshot, "tableRules": rule_admin.list_table_rules()}
    mappings = apply_content_block_rules(snapshot)
    if published_template:
        candidate = Path(published_template)
        if candidate.exists():
            revision = hashlib.sha256(candidate.read_bytes()).hexdigest()
            configuration = hashlib.sha256(json.dumps(
                {"mappings": mappings, "tableRules": snapshot["tableRules"]},
                ensure_ascii=False, sort_keys=True, default=str,
            ).encode("utf-8")).hexdigest()
            output = settings.template_path.parent / "compiled" / f"runtime-{revision[:12]}-{configuration[:12]}.docx"
            if not output.exists():
                report = compile_template(candidate, output, mappings, snapshot["tableRules"])
                if not report["valid"]:
                    raise RuntimeError(_compile_failure_message(report))
            return output, mappings, snapshot["tableRules"], {
                "template_id": str(active.get("templateId", "")) if active else "",
                "template_name": str(active.get("templateName", "")) if active else "",
                "template_code": str(active.get("templateCode", "")) if active else "",
                "template_catalog_version_id": str(active.get("versionId", "")) if active else "",
                "template_version": f"V{active['versionNo']}" if active else "V1.0",
                "template_revision": revision,
            }
    if template_version_id:
        raise RuntimeError("报告绑定的模板发布文件缺失，无法按原版本重新生成")
    if template_id:
        raise RuntimeError("所选报告模板的已发布文件缺失，请重新发布模板")
    # 走到这里说明模板库里没有可用的已发布版本。以前会静默拿基座模板顶上，
    # 生成出来的报告外观相近却不是用户配的那套模板，很难一眼看出来——直接拦住。
    workspace = rule_admin.active_workspace()
    if workspace:
        raise RuntimeError(
            f"当前模板「{workspace.get('templateName') or ''}」的 V{workspace.get('versionNo')} 版本还是"
            f"{'草稿' if workspace.get('versionStatus') == 'DRAFT' else workspace.get('versionStatus')}状态，"
            f"运行时只使用已发布版本。请在模板设计器中发布该版本后再生成报告。"
        )
    output = settings.template_path.parent / "compiled" / "runtime-report-template.docx"
    report = compile_template(settings.template_path, output, mappings, snapshot["tableRules"])
    if not report["valid"]:
        raise RuntimeError(_compile_failure_message(report))
    return output, mappings, snapshot["tableRules"], {
        "template_name": "系统基座模板",
        "template_version": "V1.0",
        "template_revision": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
