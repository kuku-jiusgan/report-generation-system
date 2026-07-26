from collections import defaultdict
from pathlib import Path
import zipfile

from lxml import etree

from .mapped_docx_generator import NS, REPORT_TAGS


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
                canonical = REPORT_TAGS.get(tag) or REPORT_TAGS.get(mapped_code)
                if canonical:
                    priority = 0 if is_header else (1 if tag == "document.code" or mapped_code == "document.code" else 2)
                    canonical_candidates[canonical].append((priority, order, value))
                order += 1

    bound_values: dict[str, str | list[str]] = {
        code: values[0] if len(values) == 1 else values for code, values in collected.items()
    }
    canonical_values: dict[str, str] = {}
    for code, candidates in canonical_candidates.items():
        ordered = sorted(candidates, key=lambda item: (item[0], item[1]))
        canonical_values[code] = next((value for _, _, value in ordered if value), "")
    return bound_values, canonical_values
