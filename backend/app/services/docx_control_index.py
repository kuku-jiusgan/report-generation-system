"""扫描模板文档，给出每个内容控件标签在 Word 里的真实位置。

字段映射里的 locationId 是按控件标签拼出来的（`word.content_control.<tag>`），
它只是标签的另一种写法，并不能证明模板里真的有这个控件：控件在 ONLYOFFICE 里
被删掉后，映射行仍然原样留着。要判断一个字段到底绑没绑上，只能回到模板文档里找。
"""

import re
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _cell_location(control: etree._Element, tables: list[etree._Element], scope: str) -> str | None:
    cells = control.xpath("ancestor::w:tc[1]", namespaces=NS)
    if not cells:
        return None
    rows = cells[0].xpath("ancestor::w:tr[1]", namespaces=NS)
    owners = cells[0].xpath("ancestor::w:tbl[1]", namespaces=NS)
    if not rows or not owners or owners[0] not in tables:
        return None
    row_cells = rows[0].xpath("./w:tc", namespaces=NS)
    table_rows = owners[0].xpath("./w:tr", namespaces=NS)
    return (f"{scope}第 {tables.index(owners[0]) + 1} 张表 "
            f"第 {table_rows.index(rows[0]) + 1} 行第 {row_cells.index(cells[0]) + 1} 格")


def _paragraph_location(control: etree._Element, paragraphs: list[etree._Element], scope: str) -> str:
    # 段落级控件会把原段落搬进 sdtContent，所以按文档顺序的段落序号来定位。
    owned = set(control.xpath(".//w:p", namespaces=NS))
    for index, paragraph in enumerate(paragraphs, start=1):
        if paragraph in owned:
            return f"{scope}第 {index} 段"
    return f"{scope}（位置未知）"


def _scan_part(root: etree._Element, scope: str, locations: dict[str, str]) -> None:
    # 表格序号与表格规则里的"Word 正文表格序号"一致，都数正文的顶层表格。
    tables = root.xpath("./w:body/w:tbl", namespaces=NS) or root.xpath(".//w:tbl", namespaces=NS)
    paragraphs = [item for item in root.xpath(".//w:p", namespaces=NS)
                  if not item.xpath("ancestor::w:tbl", namespaces=NS)]
    for control in root.xpath(".//w:sdt", namespaces=NS):
        tags = control.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
        if not tags or tags[0] in locations:
            continue
        locations[tags[0]] = (_cell_location(control, tables, scope)
                              or _paragraph_location(control, paragraphs, scope))


def _read_locations(path: str, _revision: float) -> dict[str, str]:
    template = Path(path)
    if not template.exists():
        return {}
    locations: dict[str, str] = {}
    with zipfile.ZipFile(template) as archive:
        names = [name.replace("\\", "/") for name in archive.namelist()]
        for name in ["word/document.xml", *sorted(n for n in names if re.fullmatch(r"word/header\d+\.xml", n))]:
            if name not in names:
                continue
            scope = "正文" if name == "word/document.xml" else "页眉"
            _scan_part(etree.fromstring(archive.read(name)), scope, locations)
    return locations


@lru_cache(maxsize=16)
def _cached_locations(path: str, revision: float) -> dict[str, str]:
    return _read_locations(path, revision)


def control_locations(template: Path | str | None) -> dict[str, str]:
    """控件标签 → 它在模板文档里的位置描述；模板缺失时返回空表。

    结果按文件修改时间缓存，模板在设计器里改动后会自动重新扫描。
    """
    if not template:
        return {}
    path = Path(template)
    try:
        revision = path.stat().st_mtime
    except OSError:
        return {}
    return _cached_locations(str(path), revision)


def describe_binding(locations: dict[str, str], control_tag: str) -> dict[str, Any]:
    """一条字段映射在模板文档里的真实绑定状态。"""
    tag = str(control_tag or "").strip()
    if not tag:
        return {"bound": False, "wordLocation": "", "bindingState": "未设置内容控件"}
    location = locations.get(tag)
    if not location:
        return {"bound": False, "wordLocation": "", "bindingState": "模板文档中找不到该控件"}
    return {"bound": True, "wordLocation": location, "bindingState": "已绑定"}
