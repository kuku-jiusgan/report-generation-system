"""Refresh Word fields with LibreOffice and keep the paginated document intact."""

import copy
import logging
import re
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .docx_language import write_docx_parts_atomic
from .libreoffice_fonts import libreoffice_font_env


logger = logging.getLogger(__name__)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}


class DocxFieldRefreshError(RuntimeError):
    pass


def _validated_docx(path: Path) -> bool:
    if not path.is_file() or not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            # Word and LibreOffice may write ZIP member names with either
            # separator.  Normalize before checking the required part.
            return any(name.replace("\\", "/") == "word/document.xml"
                       for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _failure_message(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "LibreOffice 未返回错误详情").strip()


def _read_parts(path: Path) -> dict[str, tuple[zipfile.ZipInfo, bytes]]:
    with zipfile.ZipFile(path) as archive:
        parts = {}
        for item in archive.infolist():
            info = copy.copy(item)
            info.filename = item.filename.replace("\\", "/")
            parts[info.filename] = (info, archive.read(item.filename))
        return parts


def _normalized_instruction(text: str) -> str:
    return " ".join(text.split())


def _inside_toc(node: etree._Element) -> bool:
    for control in node.xpath("ancestor::w:sdt", namespaces=NS):
        instruction = _normalized_instruction("".join(
            control.xpath(".//w:instrText/text()", namespaces=NS)
        ))
        if instruction == "TOC" or instruction.startswith("TOC "):
            return True
    return False


def _complex_fields(root: etree._Element) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag == f"{W}fldChar":
            field_type = node.get(f"{W}fldCharType")
            if field_type == "begin":
                stack.append({"instruction": [], "texts": [], "separated": False,
                              "node": node, "end": None,
                              "parent_field": stack[-1] if stack else None})
            elif field_type == "separate" and stack:
                stack[-1]["separated"] = True
            elif field_type == "end" and stack:
                field = stack.pop()
                field["end"] = node
                fields.append(field)
        elif node.tag == f"{W}instrText" and stack and not stack[-1]["separated"]:
            stack[-1]["instruction"].append(node.text or "")
        elif node.tag == f"{W}t" and stack and stack[-1]["separated"]:
            stack[-1]["texts"].append(node)
    return fields


def _instruction_of(field: dict[str, Any]) -> str:
    return _normalized_instruction("".join(field["instruction"]))


def _pagination_key(instruction: str) -> str:
    tokens = instruction.split()
    if not tokens:
        return ""
    field_type = tokens[0].upper()
    if field_type in {"PAGEREF", "REF"} and len(tokens) > 1:
        return f"{field_type} {tokens[1]}"
    return field_type


def _is_toc_field(field: dict[str, Any]) -> bool:
    instruction = _instruction_of(field)
    return instruction == "TOC" or instruction.startswith("TOC ")


def _field_inside_toc(field: dict[str, Any]) -> bool:
    if _inside_toc(field["node"]):
        return True
    parent = field.get("parent_field")
    while parent:
        if _is_toc_field(parent):
            return True
        parent = parent.get("parent_field")
    return False


def _is_field_part(name: str) -> bool:
    return name.endswith(".xml") and (
        name == "word/document.xml" or name.startswith("word/header")
        or name.startswith("word/footer") or name in {"word/footnotes.xml", "word/endnotes.xml"}
    )


def _common_container_range(start: etree._Element, end: etree._Element) -> list[etree._Element]:
    end_ancestors = set(end.iterancestors())
    container = next((node for node in start.iterancestors() if node in end_ancestors), None)
    if container is None:
        raise DocxFieldRefreshError("目录域的起止位置没有共同容器")

    def direct_child(node: etree._Element) -> etree._Element:
        while node.getparent() is not container:
            parent = node.getparent()
            if parent is None:
                raise DocxFieldRefreshError("无法定位目录域所在的文档块")
            node = parent
        return node

    children = list(container)
    first, last = children.index(direct_child(start)), children.index(direct_child(end))
    if first > last:
        raise DocxFieldRefreshError("目录域的起止顺序无效")
    return children[first:last + 1]


def _toc_links(root: etree._Element) -> list[etree._Element]:
    links = []
    for field in _complex_fields(root):
        instruction = _instruction_of(field)
        if instruction != "TOC" and not instruction.startswith("TOC "):
            continue
        for block in _common_container_range(field["node"], field["end"]):
            if block.tag == f"{W}hyperlink" and block.get(f"{W}anchor"):
                links.append(block)
            links.extend(block.xpath(".//w:hyperlink[@w:anchor]", namespaces=NS))
    return links


def contains_toc_field(document_path: Path) -> bool:
    """Return whether the main document contains a TOC field."""
    parts = _read_parts(document_path)
    document = parts.get("word/document.xml")
    if document is None:
        raise DocxFieldRefreshError("DOCX 缺少 Word 正文")
    root = etree.fromstring(document[1])
    return any(
        _instruction_of(field) == "TOC" or _instruction_of(field).startswith("TOC ")
        for field in _complex_fields(root)
    )


def _page_result(link: etree._Element) -> str:
    for field in _complex_fields(link):
        if _instruction_of(field).startswith("PAGEREF "):
            page = "".join(text.text or "" for text in field["texts"]).strip()
            if page:
                return page
            raise DocxFieldRefreshError("LibreOffice 刷新后的目录项缺少页码")
    texts = [str(value) for value in link.xpath(".//w:t/text()", namespaces=NS)]
    if link.xpath(".//w:tab", namespaces=NS) and texts:
        candidate = texts[-1].strip()
        if re.fullmatch(r"\d+|[ivxlcdm]+", candidate, re.IGNORECASE):
            return candidate
    raise DocxFieldRefreshError("LibreOffice 刷新后的目录项缺少页码")


def _bookmark_alias(rendered: etree._Element, rendered_anchor: str,
                    original_anchors: set[str]) -> str | None:
    if rendered_anchor in original_anchors:
        return rendered_anchor
    starts = rendered.xpath(
        ".//w:bookmarkStart[@w:name=$name]", namespaces=NS, name=rendered_anchor,
    )
    matches = set()
    for start in starts:
        paragraphs = start.xpath("ancestor::w:p[1]", namespaces=NS)
        if paragraphs:
            names = set(paragraphs[0].xpath(".//w:bookmarkStart/@w:name", namespaces=NS))
            matches.update(names & original_anchors)
    if len(matches) != 1:
        return None
    return matches.pop()


def _set_toc_page(link: etree._Element, page: str) -> None:
    page_fields = [
        field for field in _complex_fields(link)
        if _pagination_key(_instruction_of(field)).startswith("PAGEREF ")
    ]
    if len(page_fields) != 1 or not page_fields[0]["texts"]:
        raise DocxFieldRefreshError("模板目录项缺少唯一的 PAGEREF 页码域")
    texts = page_fields[0]["texts"]
    texts[0].text = page
    for text in texts[1:]:
        text.text = ""


def _merge_toc_results(original: etree._Element, rendered: etree._Element) -> None:
    original_links = _toc_links(original)
    rendered_links = _toc_links(rendered)
    if not original_links and not rendered_links:
        return
    original_by_anchor = {str(link.get(f"{W}anchor")): link for link in original_links}
    rendered_pages: dict[str, str] = {}
    original_anchors = set(original_by_anchor)
    for link in rendered_links:
        rendered_anchor = str(link.get(f"{W}anchor") or "")
        original_anchor = _bookmark_alias(rendered, rendered_anchor, original_anchors)
        if original_anchor:
            rendered_pages[original_anchor] = _page_result(link)
    missing = sorted(original_anchors - set(rendered_pages))
    if missing:
        raise DocxFieldRefreshError(
            f"LibreOffice 未能定位 {len(missing)} 个模板目录项的实际页码"
        )
    for anchor, link in original_by_anchor.items():
        _set_toc_page(link, rendered_pages[anchor])


def _simple_fields(root: etree._Element) -> list[dict[str, Any]]:
    return [
        {
            "instruction": [node.get(f"{W}instr", "")],
            "texts": node.xpath(".//w:t", namespaces=NS),
            "node": node,
        }
        for node in root.xpath(".//w:fldSimple", namespaces=NS)
        if not _inside_toc(node)
    ]


def _pagination_results(root: etree._Element) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    for field in [*_complex_fields(root), *_simple_fields(root)]:
        if _field_inside_toc(field):
            continue
        instruction = _instruction_of(field)
        if instruction.split(" ", 1)[0].upper() not in {"PAGE", "NUMPAGES", "SECTIONPAGES", "PAGEREF", "REF"}:
            continue
        results.setdefault(_pagination_key(instruction), []).append(
            "".join(text.text or "" for text in field["texts"])
        )
    return results


def _merge_pagination_results(original: etree._Element,
                              rendered_results: dict[str, list[str]]) -> None:
    offsets: dict[str, int] = {}
    for field in [*_complex_fields(original), *_simple_fields(original)]:
        if _field_inside_toc(field):
            continue
        instruction = _instruction_of(field)
        if instruction.split(" ", 1)[0].upper() not in {"PAGE", "NUMPAGES", "SECTIONPAGES", "PAGEREF", "REF"}:
            continue
        key = _pagination_key(instruction)
        values = rendered_results.get(key, [])
        index = offsets.get(key, 0)
        if index >= len(values):
            raise DocxFieldRefreshError(f"LibreOffice 未返回域“{instruction}”的刷新结果")
        texts = field["texts"]
        if not texts:
            raise DocxFieldRefreshError(f"原文件中的域“{instruction}”没有可写入的结果节点")
        texts[0].text = values[index]
        for text in texts[1:]:
            text.text = ""
        offsets[key] = index + 1


def _copy_toc_format(original: etree._Element, rendered: etree._Element) -> None:
    original_links = _toc_links(original)
    rendered_links = _toc_links(rendered)
    original_by_anchor = {str(link.get(f"{W}anchor")): link for link in original_links}
    for rendered_link in rendered_links:
        source = original_by_anchor.get(str(rendered_link.get(f"{W}anchor")))
        if source is None:
            continue
        source_paragraph = source.xpath("ancestor::w:p[1]", namespaces=NS)
        target_paragraph = rendered_link.xpath("ancestor::w:p[1]", namespaces=NS)
        if source_paragraph and target_paragraph:
            source_properties = source_paragraph[0].find(f"{W}pPr")
            target_properties = target_paragraph[0].find(f"{W}pPr")
            if source_properties is not None:
                if target_properties is None:
                    target_paragraph[0].insert(0, copy.deepcopy(source_properties))
                else:
                    target_paragraph[0].replace(target_properties, copy.deepcopy(source_properties))
        source_runs = source.xpath(".//w:r/w:rPr", namespaces=NS)
        target_runs = rendered_link.xpath(".//w:r/w:rPr", namespaces=NS)
        for source_run, target_run in zip(source_runs, target_runs):
            target_run.getparent().replace(target_run, copy.deepcopy(source_run))


def _copy_content_controls(original: etree._Element, rendered: etree._Element) -> None:
    controls = {
        str(node.xpath("string(./w:sdtPr/w:tag/@w:val)", namespaces=NS)): node
        for node in original.xpath(".//w:sdt", namespaces=NS)
        if node.xpath("string(./w:sdtPr/w:tag/@w:val)", namespaces=NS)
    }
    for node in rendered.xpath(".//w:sdt", namespaces=NS):
        tag = str(node.xpath("string(./w:sdtPr/w:tag/@w:val)", namespaces=NS))
        if tag in controls:
            node.getparent().replace(node, copy.deepcopy(controls[tag]))
    body = rendered.find(f"{W}body")
    if body is not None:
        for tag, node in controls.items():
            if not rendered.xpath(".//w:sdtPr/w:tag[@w:val=$tag]", namespaces=NS, tag=tag):
                body.insert(0, copy.deepcopy(node))


def _merge_refreshed_fields_legacy(original_path: Path, rendered_parts: dict[str, tuple[zipfile.ZipInfo, bytes]],
                                   original_parts: dict[str, tuple[zipfile.ZipInfo, bytes]]) -> None:
    rendered_results: dict[str, list[str]] = {}
    for name in sorted(rendered_parts):
        if not _is_field_part(name):
            continue
        root = etree.fromstring(rendered_parts[name][1])
        for key, values in _pagination_results(root).items():
            rendered_results.setdefault(key, []).extend(values)
    for name, (info, content) in list(original_parts.items()):
        if not _is_field_part(name):
            continue
        original_root = etree.fromstring(content)
        _merge_pagination_results(original_root, rendered_results)
        if name == "word/document.xml":
            rendered_root = etree.fromstring(rendered_parts[name][1])
            _merge_toc_results(original_root, rendered_root)
        original_parts[name] = (info, etree.tostring(
            original_root, xml_declaration=True, encoding="UTF-8", standalone=True,
        ))
    write_docx_parts_atomic(original_parts, original_path)


def _toc_display_text(link: etree._Element) -> list[etree._Element]:
    return [node for node in link.xpath(".//w:t", namespaces=NS)
            if not node.xpath("ancestor::w:fldChar", namespaces=NS)]


def _restore_native_toc(original: etree._Element, rendered: etree._Element) -> None:
    """Replace LibreOffice's static TOC entries with the original PAGEREF fields."""
    original_links = _toc_links(original)
    rendered_links = _toc_links(rendered)
    if not original_links or not rendered_links:
        return
    original_by_anchor = {str(link.get(f"{W}anchor")): link for link in original_links}
    original_anchors = set(original_by_anchor)
    matched: set[str] = set()
    for rendered_link in list(rendered_links):
        rendered_anchor = str(rendered_link.get(f"{W}anchor") or "")
        original_anchor = _bookmark_alias(rendered, rendered_anchor, original_anchors)
        if not original_anchor:
            continue
        page = _page_result(rendered_link)
        native_link = copy.deepcopy(original_by_anchor[original_anchor])
        native_link.set(f"{W}anchor", rendered_anchor)
        source_text = _toc_display_text(rendered_link)
        target_text = _toc_display_text(native_link)
        for target, source in zip(target_text, source_text):
            target.text = source.text
        _set_toc_page(native_link, page)
        rendered_link.getparent().replace(rendered_link, native_link)
        matched.add(original_anchor)
    missing = original_anchors - matched
    if missing:
        raise DocxFieldRefreshError(f"LibreOffice 未能定位 {len(missing)} 个模板目录项的实际页码")


def _remove_orphan_toc_entries(root: etree._Element) -> bool:
    bookmarks = set(root.xpath(".//w:bookmarkStart/@w:name", namespaces=NS))
    changed = False
    for link in _toc_links(root):
        if link.get(f"{W}anchor") in bookmarks:
            continue
        paragraphs = link.xpath("ancestor::w:p[1]", namespaces=NS)
        if len(paragraphs) != 1 or len(paragraphs[0].xpath(
            ".//w:hyperlink[@w:anchor]", namespaces=NS,
        )) != 1:
            raise DocxFieldRefreshError("LibreOffice 生成了无法安全移除的无效目录链接")
        paragraph = paragraphs[0]
        if paragraph.xpath(".//w:fldChar", namespaces=NS):
            link.getparent().remove(link)
        else:
            paragraph.getparent().remove(paragraph)
        changed = True
    return changed


def _static_control_segments(control: etree._Element) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    field_depth = 0
    for node in control.iter():
        if node.tag == f"{W}fldSimple":
            if current:
                segments.append("".join(current))
                current = []
        elif node.tag == f"{W}fldChar":
            field_type = node.get(f"{W}fldCharType")
            if field_type == "begin":
                if current:
                    segments.append("".join(current))
                    current = []
                field_depth += 1
            elif field_type == "end":
                if not field_depth:
                    raise DocxFieldRefreshError("内容控件中的 Word 域结束标记没有起始标记")
                field_depth -= 1
        elif node.tag == f"{W}t" and not field_depth and not any(
            ancestor.tag == f"{W}fldSimple" for ancestor in node.iterancestors()
        ):
            current.append(node.text or "")
    if current:
        segments.append("".join(current))
    if field_depth:
        raise DocxFieldRefreshError("内容控件中的 Word 域缺少结束标记")
    return segments


def _validate_rendered_content(original: etree._Element, rendered: etree._Element) -> None:
    # ponytail: 这里只校验已绑定静态文字；如需验证图片和表格无损，应增加 OOXML 结构清单比对。
    rendered_text = "".join(rendered.xpath(".//w:body//w:t/text()", namespaces=NS))
    for control in original.xpath(".//w:sdt[w:sdtPr/w:tag/@w:val]", namespaces=NS):
        for value in _static_control_segments(control):
            if value.strip() and value not in rendered_text:
                tag = str(control.xpath("string(./w:sdtPr/w:tag/@w:val)", namespaces=NS))
                raise DocxFieldRefreshError(f"LibreOffice 刷新后丢失了已填内容：{tag}")


def _merge_refreshed_fields(original_path: Path, rendered_path: Path) -> None:
    original_parts = _read_parts(original_path)
    rendered_parts = _read_parts(rendered_path)
    original_root = etree.fromstring(original_parts["word/document.xml"][1])
    rendered_root = etree.fromstring(rendered_parts["word/document.xml"][1])
    _validate_rendered_content(original_root, rendered_root)
    _remove_orphan_toc_entries(rendered_root)
    _restore_native_toc(original_root, rendered_root)
    rendered_parts["word/document.xml"] = (
        rendered_parts["word/document.xml"][0],
        etree.tostring(rendered_root, xml_declaration=True, encoding="UTF-8", standalone=True),
    )
    # Keep LibreOffice's rendered layout, but update ordinary pagination fields
    # from the same rendered document instead of replacing the native TOC.
    for name, (info, content) in list(rendered_parts.items()):
        if not _is_field_part(name):
            continue
        rendered_part_root = etree.fromstring(content)
        _merge_pagination_results(rendered_part_root, _pagination_results(rendered_part_root))
        rendered_parts[name] = (info, etree.tostring(
            rendered_part_root, xml_declaration=True, encoding="UTF-8", standalone=True,
        ))
    write_docx_parts_atomic(rendered_parts, original_path)


def refresh_docx_fields(document_path: Path, executable: str = "libreoffice",
                        timeout_seconds: float = 120.0,
                        python_executable: str = "/usr/bin/python3") -> None:
    """Refresh fields and save the body and TOC from the same pagination pass."""
    path = document_path.resolve()
    if not _validated_docx(path):
        raise DocxFieldRefreshError(f"待刷新文件不是有效的 DOCX：{path.name}")
    if timeout_seconds <= 0:
        raise DocxFieldRefreshError("DOCX 域刷新超时时间必须大于 0 秒")

    logger.info("开始刷新 DOCX 目录与页码 document=%s", path.name)
    with tempfile.TemporaryDirectory(prefix=".docx-field-refresh-", dir=path.parent) as directory:
        workspace = Path(directory)
        input_dir = workspace / "input"
        output_dir = workspace / "output"
        profile_dir = workspace / "profile"
        input_dir.mkdir()
        output_dir.mkdir()
        profile_dir.mkdir()
        temporary_input = input_dir / path.name
        converted = output_dir / path.name
        # LibreOffice requires canonical ZIP member separators.  Word files
        # created on Windows commonly contain backslashes, so normalize the
        # temporary input archive while keeping the source untouched.
        write_docx_parts_atomic(_read_parts(path), temporary_input)

        pipe_name = f"report_docx_fields_{uuid.uuid4().hex}"
        office_command = [
            executable, "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
            "--norestore", f"-env:UserInstallation={profile_dir.as_uri()}",
            f"--accept=pipe,name={pipe_name};urp;StarOffice.ComponentContext",
        ]
        worker_command = [
            python_executable, str(Path(__file__).with_name("libreoffice_field_worker.py")),
            pipe_name, str(temporary_input), str(converted), str(timeout_seconds),
        ]
        try:
            office_process = subprocess.Popen(
                office_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=libreoffice_font_env(),
            )
        except FileNotFoundError as error:
            raise DocxFieldRefreshError(
                f"LibreOffice 不可用：找不到可执行文件“{executable}”"
            ) from error
        except OSError as error:
            raise DocxFieldRefreshError(f"LibreOffice 启动失败：{error}") from error
        try:
            result = subprocess.run(
                worker_command, capture_output=True, text=True,
                timeout=timeout_seconds + 10, check=False,
            )
        except FileNotFoundError as error:
            raise DocxFieldRefreshError(
                f"LibreOffice UNO Python 不可用：找不到可执行文件“{python_executable}”"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise DocxFieldRefreshError(
                f"LibreOffice 刷新目录与页码超时（{timeout_seconds:g} 秒）"
            ) from error
        except OSError as error:
            raise DocxFieldRefreshError(f"LibreOffice 域刷新进程启动失败：{error}") from error
        finally:
            if office_process.poll() is None:
                office_process.terminate()
                try:
                    office_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    office_process.kill()
                    office_process.wait(timeout=5)

        if result.returncode != 0:
            raise DocxFieldRefreshError(f"LibreOffice 刷新目录与页码失败：{_failure_message(result)}")
        if not _validated_docx(converted):
            raise DocxFieldRefreshError(
                f"LibreOffice 未生成有效的刷新文件：{_failure_message(result)}"
            )
        _merge_refreshed_fields(path, converted)
    logger.info("DOCX 目录与页码刷新完成 document=%s", path.name)
