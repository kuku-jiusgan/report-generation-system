import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from fastapi import HTTPException, UploadFile

from backend.app.services.protocol_document import (
    PROTOCOL_MEDIA_TYPE, apply_protocol_document, validate_protocol_document,
)
from backend.app.source_api import create_source_router


def word_document() -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            f'<Override PartName="/word/document.xml" ContentType="{PROTOCOL_MEDIA_TYPE}.main+xml"/>'
            '</Types>'
        ))
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>验证方案</w:t></w:r></w:p></w:body></w:document>'
        ))
    return buffer.getvalue()


def source_router(tmp_path: Path):
    database = MagicMock()
    database.create_source.side_effect = lambda value: value
    settings = SimpleNamespace(api_prefix="/api/v1", uploads_dir=tmp_path, max_upload_mb=1)
    router = create_source_router(database, settings, MagicMock(), lambda value: value)
    endpoints = {next(iter(route.methods)): route.endpoint for route in router.routes
                 if route.path == "/api/v1/source-documents"}
    return database, router, endpoints["POST"]


def test_upload_word_protocol_keeps_original_and_download_type(tmp_path: Path):
    database, router, upload = source_router(tmp_path)
    content = word_document()
    result = asyncio.run(upload(UploadFile(filename="方案.docx", file=io.BytesIO(content)), user={}))
    assert result["source_type"] == "PROTOCOL"
    assert (tmp_path / result["stored_name"]).read_bytes() == content
    database.get_source.return_value = result
    preview = next(route.endpoint for route in router.routes if route.path.endswith("/preview"))
    response = preview(result["id"], user={})
    assert response.media_type == PROTOCOL_MEDIA_TYPE
    assert response.filename == "方案.docx"
    extract = next(route.endpoint for route in router.routes if route.path.endswith("/extract"))
    database.list_lims_fields.return_value = []
    database.list_system_field_rules.return_value = []
    extract(result["id"], user={})
    database.update_source_payload.assert_called_once()
    assert database.update_source_payload.call_args.args[1]['_meta']['fields'] == {}


@pytest.mark.parametrize("name,content,status", [
    ("方案.doc", b"legacy", 400), ("方案.docx", b"invalid", 422), ("方案.docx", b"", 400),
    ("方案.docx", b"a" * (1024 * 1024 + 1), 413),
])
def test_invalid_protocol_is_rejected_without_saving(tmp_path: Path, name, content, status):
    database, _, upload = source_router(tmp_path)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(upload(UploadFile(filename=name, file=io.BytesIO(content)), user={}))
    assert caught.value.status_code == status
    database.create_source.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_protocol_attachment_has_independent_namespace():
    data = {"source_payloads": {"LIMS": {"samples": []}, "WORD": {"boundValues": {}}}}
    source = {"id": "protocol-id", "file_name": "方案.docx", "source_type": "PROTOCOL", "sha256": "hash"}
    apply_protocol_document(data, source, "/api/v1")
    assert data["source_payloads"]["PROTOCOL_DOCUMENT"]["fileName"] == "方案.docx"
    assert data["source_payloads"]["LIMS"] == {"samples": []}
    assert data["source_payloads"]["WORD"] == {"boundValues": {}}
    with pytest.raises(ValueError, match="方案文件类型无效"):
        apply_protocol_document(data, {**source, "source_type": "PDF"}, "/api/v1")


def test_protocol_expanded_size_limit(tmp_path: Path):
    path = tmp_path / "方案.docx"
    path.write_bytes(word_document())
    with pytest.raises(ValueError, match="解压后大小"):
        validate_protocol_document(path, 1)
