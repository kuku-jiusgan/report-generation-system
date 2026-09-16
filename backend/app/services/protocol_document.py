from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


PROTOCOL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def validate_protocol_document(path: Path, max_bytes: int) -> None:
    """校验 Word 方案容器和正文，不解压文件，也不执行文档内容。"""
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if sum(entry.file_size for entry in entries) > max_bytes:
                raise ValueError("Word 方案解压后大小超过上传限制")
            if any(entry.flag_bits & 1 for entry in entries):
                raise ValueError("不支持加密的 Word 方案")
            if "word/vbaProject.bin" in archive.namelist():
                raise ValueError("不支持包含宏的 Word 方案")
            types = ElementTree.fromstring(archive.read("[Content_Types].xml"))
            if not any(entry.get("PartName") == "/word/document.xml" and
                       entry.get("ContentType") == f"{PROTOCOL_MEDIA_TYPE}.main+xml"
                       for entry in types):
                raise ValueError("方案必须是 DOCX 格式的 Word 文档")
            document = ElementTree.fromstring(archive.read("word/document.xml"))
            if document.tag != f"{{{_WORD_NS}}}document" or document.find(f"{{{_WORD_NS}}}body") is None:
                raise ValueError("Word 方案缺少有效正文")
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError) as error:
        raise ValueError("Word 方案文件损坏或格式无效，请重新另存为 DOCX 后上传") from error


def apply_protocol_document(data: dict[str, Any], source: dict[str, Any], api_prefix: str) -> None:
    if source.get("source_type") != "PROTOCOL":
        raise ValueError("方案文件类型无效，请上传 DOCX 格式的 Word 方案")
    data.setdefault("source_payloads", {})["PROTOCOL_DOCUMENT"] = {
        "id": source["id"], "fileName": source["file_name"], "sha256": source.get("sha256", ""),
        "downloadUrl": f"{api_prefix}/source-documents/{source['id']}/preview",
    }
