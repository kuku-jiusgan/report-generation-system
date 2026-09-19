from pathlib import Path
from typing import Any

from .docx_validation import DOCX_MEDIA_TYPE as PROTOCOL_MEDIA_TYPE, validate_docx_document



def validate_protocol_document(path: Path, max_bytes: int) -> None:
    validate_docx_document(path, max_bytes, "Word 方案")


def apply_protocol_document(data: dict[str, Any], source: dict[str, Any], api_prefix: str) -> None:
    if source.get("source_type") != "PROTOCOL":
        raise ValueError("方案文件类型无效，请上传 DOCX 格式的 Word 方案")
    data.setdefault("source_payloads", {})["PROTOCOL_DOCUMENT"] = {
        "id": source["id"], "fileName": source["file_name"], "sha256": source.get("sha256", ""),
        "downloadUrl": f"{api_prefix}/source-documents/{source['id']}/preview",
    }
