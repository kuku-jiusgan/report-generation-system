import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any

from .docx_language import ensure_simplified_chinese


class TemplateFileStore:
    """Own editable template documents; published artifacts live outside this store."""

    def __init__(self, repository: Any, template_path: Path):
        self.repository = repository
        self.template_path = template_path
        self.draft_dir = template_path.parent / "drafts"
        self.published_dir = template_path.parent / "published"
        self.draft_dir.mkdir(parents=True, exist_ok=True)

    def version_draft_path(self, version_id: str) -> Path:
        return self.draft_dir / f"report-template-{version_id}.docx"

    def active_draft_path(self) -> Path:
        workspace = self.repository.active_workspace()
        version_id = workspace["versionId"] if workspace else "default"
        return self.version_draft_path(version_id)

    def ensure_version_draft(self, version_id: str) -> Path:
        version = self.repository.get_template_version(version_id)
        if not version:
            raise ValueError("模板版本不存在")
        if version["status"] != "DRAFT":
            raise ValueError("已发布模板不可进入编辑器，请创建新的草稿版本")
        draft = self.version_draft_path(version_id)
        if draft.exists():
            ensure_simplified_chinese(draft)
            return draft
        stored = Path(version["templateFile"]) if version.get("templateFile") else None
        source = stored if stored and stored.exists() else self.template_path
        shutil.copy2(source, draft)
        self.repository.set_template_version_file(version_id, str(draft))
        ensure_simplified_chinese(draft)
        return draft

    def ensure_active_draft(self) -> Path:
        workspace = self.repository.active_workspace()
        if not workspace:
            return self.template_path
        return self.ensure_version_draft(str(workspace["versionId"]))

    def initialize_version(self, version_id: str, source: Path) -> Path:
        version = self.repository.get_template_version(version_id)
        if not version:
            raise ValueError("模板版本不存在")
        if version["status"] != "DRAFT":
            raise ValueError("只能初始化草稿模板文件")
        actual_source = source if source.exists() else self.template_path
        target = self.version_draft_path(version_id)
        if actual_source.resolve() != target.resolve():
            shutil.copy2(actual_source, target)
        self.repository.set_template_version_file(version_id, str(target))
        self.repository.set_version_document_key(version_id, None)
        return target

    def publish_version(self, template_id: str, version_id: str, source: Path) -> Path:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        target_dir = self.published_dir / template_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{version_id}-{digest}.docx"
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise RuntimeError("发布模板文件哈希冲突")
            return target
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target
