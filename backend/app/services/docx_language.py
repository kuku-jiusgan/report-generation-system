import copy
import uuid
import zipfile
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def write_docx_parts_atomic(parts: dict[str, tuple[zipfile.ZipInfo, bytes]], output: Path) -> None:
    """先写唯一临时文件再原子替换目标，避免并发读到写了一半的 docx。"""
    temporary = output.with_name(f"{output.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
            for info, content in parts.values():
                target.writestr(info, content)
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def normalize_part_languages(parts: dict[str, tuple[zipfile.ZipInfo, bytes]]) -> None:
    """Set Simplified Chinese on the XML parts of an in-memory DOCX archive."""
    for name, (info, content) in list(parts.items()):
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        try:
            root = etree.fromstring(content)
        except etree.XMLSyntaxError:
            continue
        changed = False
        for language in root.xpath(".//w:lang", namespaces={"w": W_NS}):
            language.set(W + "val", "zh-CN")
            language.set(W + "eastAsia", "zh-CN")
            language.attrib.pop(W + "bidi", None)
            changed = True
        for language in root.xpath(".//w:themeFontLang", namespaces={"w": W_NS}):
            language.set(W + "val", "zh-CN")
            language.set(W + "eastAsia", "zh-CN")
            language.attrib.pop(W + "bidi", None)
            changed = True
        if changed:
            parts[name] = (info, etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            ))


def ensure_simplified_chinese(path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".lang.tmp")
    changed = False
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            info = copy.copy(item)
            name = item.filename.replace("\\", "/")
            content = source.read(item.filename)
            if name.startswith("word/") and name.endswith(".xml"):
                try:
                    root = etree.fromstring(content)
                    for language in root.xpath(".//w:lang", namespaces={"w": W_NS}):
                        if language.get(W + "val") != "zh-CN" or language.get(W + "eastAsia") != "zh-CN" or W + "bidi" in language.attrib:
                            changed = True
                        language.set(W + "val", "zh-CN")
                        language.set(W + "eastAsia", "zh-CN")
                        language.attrib.pop(W + "bidi", None)
                    for theme_language in root.xpath(".//w:themeFontLang", namespaces={"w": W_NS}):
                        if theme_language.get(W + "val") != "zh-CN" or theme_language.get(W + "eastAsia") != "zh-CN":
                            changed = True
                        theme_language.set(W + "val", "zh-CN")
                        theme_language.set(W + "eastAsia", "zh-CN")
                    if name == "word/styles.xml":
                        defaults = root.find(W + "docDefaults")
                        if defaults is None:
                            defaults = etree.Element(W + "docDefaults")
                            root.insert(0, defaults)
                        run_defaults = defaults.find(W + "rPrDefault")
                        if run_defaults is None:
                            run_defaults = etree.SubElement(defaults, W + "rPrDefault")
                        run_properties = run_defaults.find(W + "rPr")
                        if run_properties is None:
                            run_properties = etree.SubElement(run_defaults, W + "rPr")
                        default_language = run_properties.find(W + "lang")
                        if default_language is None:
                            default_language = etree.SubElement(run_properties, W + "lang")
                            changed = True
                        if default_language.get(W + "val") != "zh-CN" or default_language.get(W + "eastAsia") != "zh-CN":
                            changed = True
                        default_language.set(W + "val", "zh-CN")
                        default_language.set(W + "eastAsia", "zh-CN")
                    content = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                except etree.XMLSyntaxError:
                    pass
            info.filename = name
            target.writestr(info, content)
    if changed:
        temporary.replace(path)
    else:
        temporary.unlink()
