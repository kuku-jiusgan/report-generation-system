import base64
import logging
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree


logger = logging.getLogger(__name__)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W_NS}
W = f"{{{W_NS}}}"


def _tag(control: etree._Element) -> str:
    values = control.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
    return str(values[0]) if values else ""


def _load_image(value: str) -> tuple[bytes, str] | None:
    if value.startswith("data:image/"):
        try:
            header, encoded = value.split(",", 1)
            media_type = header[5:].split(";", 1)[0]
            content = base64.b64decode(encoded, validate=True)
            if not content or len(content) > 8 * 1024 * 1024:
                raise ValueError("图片大小无效")
            return content, media_type
        except (ValueError, TypeError) as error:
            logger.warning("内嵌图片数据无效: error=%s", error)
            return None
    try:
        request = urllib.request.Request(value, headers={"User-Agent": "ReportGenerationSystem/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = str(response.headers.get_content_type() or "")
            if not content_type.startswith("image/"):
                logger.warning("图片地址返回的不是图片: url=%s content_type=%s", value, content_type)
                return None
            return response.read(8 * 1024 * 1024), content_type
    except Exception as error:
        logger.warning("图片下载失败: url=%s error=%s", value, error)
        return None


def _set_control_image(control: etree._Element, relationship_id: str, name: str,
                       wide: bool = False) -> None:
    content = control.find(W + "sdtContent")
    if content is None:
        return
    for child in list(content):
        content.remove(child)
    paragraph = etree.SubElement(content, W + "p")
    run = etree.SubElement(paragraph, W + "r")
    drawing = etree.SubElement(run, W + "drawing")
    width, height = ((4_860_000, 2_610_000) if wide else (914_400, 914_400))
    drawing_xml = f'''<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
      xmlns:r="{R_NS}" distT="0" distB="0" distL="0" distR="0">
      <wp:extent cx="{width}" cy="{height}"/><wp:docPr id="1" name="{name}"/>
      <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
      <pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>
      <pic:blipFill><a:blip r:embed="{relationship_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
      <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width}" cy="{height}"/></a:xfrm>
      <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>
      </a:graphicData></a:graphic></wp:inline>'''
    drawing.append(etree.fromstring(drawing_xml.encode()))


def embed_image_controls(parts: dict[str, tuple[zipfile.ZipInfo, bytes]],
                         roots: dict[str, etree._Element], mappings: list[dict[str, Any]]) -> None:
    image_tags = {str(item.get("controlTag")): item for item in mappings
                  if item.get("dataType") == "image" and item.get("controlTag")}
    if not image_tags:
        return
    content_types = etree.fromstring(parts["[Content_Types].xml"][1])

    def register_extension(extension: str, media_type: str) -> None:
        if content_types.xpath(f"./*[local-name()='Default'][@Extension='{extension}']"):
            return
        content_types.append(etree.Element(f"{{{CONTENT_TYPES_NS}}}Default", Extension=extension,
                                           ContentType=media_type))

    for part_name, root in roots.items():
        rels_name = "word/_rels/" + Path(part_name).name + ".rels"
        if rels_name not in parts:
            continue
        rels = etree.fromstring(parts[rels_name][1])
        next_id = max([int(str(item.get("Id", "rId0")).replace("rId", "0"))
                       for item in rels] + [0]) + 1
        for control in root.xpath(".//w:sdt", namespaces=NS):
            tag = _tag(control)
            if tag not in image_tags:
                continue
            value = "".join(control.xpath(".//w:t/text()", namespaces=NS)).strip()
            if not value.startswith(("http://", "https://", "data:image/")):
                continue
            downloaded = _load_image(value)
            if not downloaded:
                continue
            image_bytes, content_type = downloaded
            extension = ("jpg" if content_type == "image/jpeg"
                         else content_type.split("/", 1)[-1].split("+")[0]).lower()
            register_extension(extension, content_type)
            media_name = f"word/media/structure-{uuid.uuid4().hex}.{extension}"
            info = zipfile.ZipInfo(media_name)
            info.compress_type = zipfile.ZIP_DEFLATED
            parts[media_name] = (info, image_bytes)
            relationship_id = f"rId{next_id}"
            next_id += 1
            etree.SubElement(rels, f"{{{PKG_REL_NS}}}Relationship", Id=relationship_id,
                             Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                             Target="media/" + Path(media_name).name)
            wide = "IMAGE_FIT_WIDE" in str(image_tags[tag].get("fillRule") or "")
            _set_control_image(control, relationship_id, Path(media_name).name, wide)
        parts[rels_name] = (parts[rels_name][0], etree.tostring(
            rels, xml_declaration=True, encoding="UTF-8", standalone=True))
    parts["[Content_Types].xml"] = (parts["[Content_Types].xml"][0], etree.tostring(
        content_types, xml_declaration=True, encoding="UTF-8", standalone=True))
