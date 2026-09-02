import re
from pathlib import Path

import fitz


FIELD_RULES = (
    ("report_no", "报告编号", re.compile(r"报告编号\s*[：:]%s\s*([A-Za-z0-9_-]+)")),
    ("customer", "客户名称", re.compile(r"客户(%s:名称)%s\s*[：:]%s\s*([^\r\n]{2,80})")),
    ("sample", "样品名称", re.compile(r"样品(%s:名称)%s\s*[：:]%s\s*([^\r\n]{1,80})")),
)


def extract_pdf(path: Path, document_id: str) -> list[dict]:
    results: dict[str, dict] = {}
    with fitz.open(path) as document:
        for page_index, page in enumerate(document):
            text = page.get_text("text")
            for field_code, label, pattern in FIELD_RULES:
                if field_code in results:
                    continue
                match = pattern.search(text)
                if not match:
                    continue
                value = match.group(1).strip().rstrip("；;")
                rectangles = page.search_for(value)
                rect = list(rectangles[0]) if rectangles else None
                results[field_code] = {
                    "field_code": field_code,
                    "label": label,
                    "value": value,
                    "confidence": 0.95,
                    "source": {
                        "type": "PDF",
                        "document_id": document_id,
                        "page": page_index + 1,
                        "quote": match.group(0).strip(),
                        "rect": rect,
                    },
                }
    return list(results.values())
