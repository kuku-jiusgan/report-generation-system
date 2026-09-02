import shutil
import uuid
from pathlib import Path
from typing import Any, Callable
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from ..services.rule_admin import RuleAdminRepository
from ..services.template_compiler import compile_template

def register_publishing_routes(router: APIRouter, repository: RuleAdminRepository,
                               ensure_draft_template: Callable[[], Path],
                               active_draft_template: Callable[[], Path], compiled_dir: Path) -> None:
    def run_compile() -> tuple[Path, dict[str, Any]]:
        snapshot = repository.snapshot(); output = compiled_dir / f"report-template-bound-{uuid.uuid4().hex[:8]}.docx"
        return output, compile_template(ensure_draft_template(), output, snapshot["mappings"], snapshot["tableRules"])
    @router.post('/validate')
    def validate_rules() -> dict[str, Any]:
        output, report = run_compile(); report['previewTemplate'] = output.name; return report
    @router.post('/publish')
    def publish_rules(item: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            output, report = run_compile()
            if not report['valid']: raise HTTPException(422, {'message': '规则校验失败，不能发布', 'validation': report})
            snapshot = repository.snapshot(); version_file = active_draft_template(); shutil.copy2(output, version_file)
            return repository.publish_active_template_version(snapshot, report, str(version_file))
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
