from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def validate_docx_document(path: Path, max_bytes: int, label: str = "Word 文档") -> None:
    """校验 DOCX 容器和正文，不解压到磁盘，也不执行文档内容。"""
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if sum(entry.file_size for entry in entries) > max_bytes:
                raise ValueError(f"{label}解压后大小超过限制")
            if any(entry.flag_bits & 1 for entry in entries):
                raise ValueError(f"不支持加密的{label}")
            if "word/vbaProject.bin" in archive.namelist():
                raise ValueError(f"不支持包含宏的{label}")
            types = ElementTree.fromstring(archive.read("[Content_Types].xml"))
            if not any(
                entry.get("PartName") == "/word/document.xml"
                and entry.get("ContentType") == f"{DOCX_MEDIA_TYPE}.main+xml"
                for entry in types
            ):
                raise ValueError(f"{label}必须是 DOCX 格式")
            document = ElementTree.fromstring(archive.read("word/document.xml"))
            if document.tag != f"{{{_WORD_NS}}}document" or document.find(f"{{{_WORD_NS}}}body") is None:
                raise ValueError(f"{label}缺少有效正文")
    except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError) as error:
        raise ValueError(f"{label}损坏或格式无效，请重试") from error
