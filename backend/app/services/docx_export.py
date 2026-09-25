"""报告导出只保留控件内容，工作文档继续用于在线编辑和字段同步。"""

import copy
from contextlib import nullcontext
import io
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import Response
from lxml import etree

from .docx_language import W, W_NS, write_docx_parts_atomic

logger = logging.getLogger(__name__)
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _export_parts(source: Path) -> dict[str, tuple[zipfile.ZipInfo, bytes]]:
    parts = {}
    removed = 0
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            info = copy.copy(item)
            info.filename = item.filename.replace("\\", "/")
            content = archive.read(item)
            if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                root = etree.fromstring(content)
                controls = root.xpath(".//w:sdt", namespaces={"w": W_NS})
                for control in reversed(controls):
                    contents = control.findall(W + "sdtContent")
                    if len(contents) != 1:
                        raise ValueError("报告定位控件结构异常：必须包含唯一的内容节点")
                    parent = control.getparent()
                    index = parent.index(control)
                    for child in list(contents[0]):
                        parent.insert(index, child)
                        index += 1
                    parent.remove(control)
                if controls:
                    removed += len(controls)
                    content = etree.tostring(
                        root, xml_declaration=True, encoding="UTF-8", standalone=True,
                    )
            parts[info.filename] = (info, content)
    logger.info("报告导出定位控件清理完成 count=%s", removed)
    return parts


def _export_source(source: Path, refresh_fields: Callable[[Path], None] | None):
    if refresh_fields is None:
        return nullcontext(source)
    directory = tempfile.TemporaryDirectory(prefix=".docx-export-")
    temporary = Path(directory.name) / source.name
    shutil.copy2(source, temporary)
    try:
        refresh_fields(temporary)
    except BaseException:
        directory.cleanup()
        raise
    return _TemporaryExportSource(directory, temporary)


class _TemporaryExportSource:
    def __init__(self, directory: tempfile.TemporaryDirectory, path: Path):
        self._directory = directory
        self.path = path

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, *_: object) -> None:
        self._directory.cleanup()


def export_docx_bytes(source: Path, *, refresh_fields: Callable[[Path], None] | None = None) -> bytes:
    with _export_source(source, refresh_fields) as prepared:
        parts = _export_parts(prepared)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for info, content in parts.values():
                archive.writestr(info, content)
        return output.getvalue()


def write_export_docx(source: Path, output: Path,
                      *, refresh_fields: Callable[[Path], None] | None = None) -> None:
    with _export_source(source, refresh_fields) as prepared:
        write_docx_parts_atomic(_export_parts(prepared), output)


def export_docx_response(source: Path, title: str,
                         *, refresh_fields: Callable[[Path], None] | None = None) -> Response:
    try:
        content = export_docx_bytes(source, refresh_fields=refresh_fields)
    except Exception as error:
        logger.exception("报告下载定位控件清理失败")
        raise HTTPException(422, f"报告导出失败：{error}") from error
    return Response(content, media_type=DOCX_MEDIA_TYPE, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(title + '.docx', safe='')}",
    })
