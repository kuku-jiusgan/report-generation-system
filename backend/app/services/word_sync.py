from collections import defaultdict
from pathlib import Path
import zipfile

from lxml import etree

from .mapped_docx_generator import NS


def _control_tag(control: etree._Element) -> str:
    values = control.xpath("./w:sdtPr/w:tag/@w:val", namespaces=NS)
    if not values:
        values = control.xpath("./w:sdtPr/w:alias/@w:val", namespaces=NS)
    return str(values[0]).strip() if values else ""


def _control_text(control: etree._Element) -> str:
    return "".join(control.xpath("./w:sdtContent//w:t/text()", namespaces=NS)).strip()


def read_bound_values(path: Path, mappings: list[dict]) -> tuple[dict[str, str | list[str]], dict[str, str]]:
    """Read tagged Word controls and return mapped values plus canonical report fields."""
    tag_to_field = {
        str(item.get("controlTag") or ""): str(item.get("fieldCode") or "")
        for item in mappings if item.get("controlTag")
    }
    # 控件写回哪个报告固定字段，取自映射规则的“报告字段绑定”配置，
    # 以前是 report_fields 里的常量表，设计器看不到也改不了。
    report_bindings: dict[str, str] = {}
    for item in mappings:
        binding = str(item.get("reportBindingCode") or "")
        if not binding:
            continue
        for key in (str(item.get("controlTag") or ""), str(item.get("fieldCode") or "")):
            if key:
                report_bindings[key] = binding
    collected: dict[str, list[str]] = defaultdict(list)
    canonical_candidates: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    order = 0
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        parts = sorted(name for name in names if name.startswith("word/header") and name.endswith(".xml"))
        if "word/document.xml" in names:
            parts.append("word/document.xml")
        for part in parts:
            root = etree.fromstring(archive.read(part))
            is_header = part.startswith("word/header")
            for control in root.xpath("//w:sdt", namespaces=NS):
                tag = _control_tag(control)
                if not tag:
                    continue
                value = _control_text(control)
                mapped_code = tag_to_field.get(tag) or tag
                collected[mapped_code].append(value)
                canonical = report_bindings.get(tag) or report_bindings.get(mapped_code)
                if canonical:
                    # 页眉控件优先，其余按文档顺序取第一个非空值
                    canonical_candidates[canonical].append((0 if is_header else 1, order, value))
                order += 1

    bound_values: dict[str, str | list[str]] = {
        code: values[0] if len(values) == 1 else values for code, values in collected.items()
    }
    canonical_values: dict[str, str] = {}
    for code, candidates in canonical_candidates.items():
        ordered = sorted(candidates, key=lambda item: (item[0], item[1]))
        canonical_values[code] = next((value for _, _, value in ordered if value), "")
    return bound_values, canonical_values
