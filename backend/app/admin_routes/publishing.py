import uuid
from pathlib import Path
from typing import Any, Callable
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from ..services.rule_admin import RuleAdminRepository
from ..services.template_compiler import compile_template

def register_publishing_routes(router: APIRouter, repository: RuleAdminRepository,
                               ensure_draft_template: Callable[[], Path],
                               save_draft_template: Callable[[], dict[str, Any]],
                               publish_version_document: Callable[[str, str, Path], Path],
                               compiled_dir: Path,
                               apply_content_block_rules: Callable[[dict[str, Any]], list[dict[str, Any]]]) -> None:
    def run_compile() -> tuple[Path, dict[str, Any]]:
        snapshot = repository.snapshot()
        output = compiled_dir / f"report-template-bound-{uuid.uuid4().hex[:8]}.docx"
        mappings = apply_content_block_rules(snapshot)
        return output, compile_template(ensure_draft_template(), output, mappings, snapshot["tableRules"])
    def require_unchanged_draft(version_id: str) -> dict[str, Any]:
        current = repository.active_workspace()
        if (not current or current.get("versionId") != version_id
                or current.get("versionStatus") != "DRAFT"):
            raise HTTPException(409, "模板草稿在处理期间发生变化，请重新打开后再发布")
        return current
    @router.post('/validate')
    def validate_rules() -> dict[str, Any]:
        save_draft_template()
        output, report = run_compile(); report['previewTemplate'] = output.name; return report
    @router.post('/publish')
    def publish_rules(item: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            active = repository.active_workspace()
            if not active or active.get("versionStatus") != "DRAFT":
                raise HTTPException(409, "只有草稿版本可以发布")
            save_draft_template()
            require_unchanged_draft(str(active["versionId"]))
            output, report = run_compile()
            current = require_unchanged_draft(str(active["versionId"]))
            if not report['valid']: raise HTTPException(422, {'message': '规则校验失败，不能发布', 'validation': report})
            artifact = publish_version_document(current["templateId"], current["versionId"], output)
            published = repository.publish_active_template_version(
                repository.snapshot(), report, str(artifact),
            )
            return published
        except HTTPException: raise
        except Exception as error: raise HTTPException(500, f'发布模板版本失败：{error}') from error
    @router.get('/versions')
    def list_versions() -> list[dict[str, Any]]:
        active = repository.active_workspace(); return repository.list_template_versions(active['templateId']) if active else []
    @router.get('/compiled/{file_name}')
    def download_compiled(file_name: str) -> FileResponse:
        safe_name = Path(file_name).name; path = compiled_dir / safe_name
        if not path.exists() or path.parent.resolve() != compiled_dir.resolve(): raise HTTPException(404, '编译模板不存在')
        return FileResponse(path, filename=safe_name)
