"""报告导出只保留控件内容，工作文档继续用于在线编辑和字段同步。"""

import copy
import io
import logging
import zipfile
from pathlib import Path
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


def export_docx_bytes(source: Path) -> bytes:
    parts = _export_parts(source)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, content in parts.values():
            archive.writestr(info, content)
    return output.getvalue()


def write_export_docx(source: Path, output: Path) -> None:
    write_docx_parts_atomic(_export_parts(source), output)


def export_docx_response(source: Path, title: str) -> Response:
    try:
        content = export_docx_bytes(source)
    except Exception as error:
        logger.exception("报告下载定位控件清理失败")
        raise HTTPException(422, f"报告导出失败：{error}") from error
    return Response(content, media_type=DOCX_MEDIA_TYPE, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(title + '.docx', safe='')}",
    })
