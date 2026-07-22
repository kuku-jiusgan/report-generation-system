import hashlib
from pathlib import Path
import fitz
from .models import ExtractionRule, ExtractResponse, SourceType
from .rule_engine import find_in_text, from_oracle, missing

MAX_PDF_BYTES = 100 * 1024 * 1024

def extract(pdf_path: Path, rules: list[ExtractionRule], oracle_row: dict[str, object]) -> ExtractResponse:
    data = pdf_path.read_bytes()
    if len(data) > MAX_PDF_BYTES: raise ValueError("PDF exceeds 100 MB")
    if not data.startswith(b"%PDF-"): raise ValueError("File signature is not PDF")
    digest = hashlib.sha256(data).hexdigest()
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF is damaged or encrypted") from exc
    pages = [(i + 1, page.get_text("text")) for i, page in enumerate(doc)]
    results = []
    for rule in rules:
        if rule.sourceType == SourceType.ORACLE:
            results.append(from_oracle(rule, oracle_row))
        elif rule.locator.kind in {"regex", "anchor_regex"}:
            results.append(find_in_text(rule, pages))
        elif rule.locator.kind == "bbox":
            page_no = rule.locator.page_from
            if page_no > len(doc): results.append(missing(rule,"PDF",page_no)); continue
            rect = fitz.Rect(rule.locator.bbox)
            raw = doc[page_no - 1].get_textbox(rect).strip()
            if not raw: results.append(missing(rule,"PDF bbox",page_no)); continue
            from .rule_engine import normalize
            value, errors = normalize(raw, rule)
            from .models import FieldResult, Evidence
            results.append(FieldResult(fieldCode=rule.fieldCode,label=rule.label,rawValue=raw,normalizedValue=value,status="WARNING" if errors else "VALID",targetControlTag=rule.targetControlTag,evidence=Evidence(sourceType=SourceType.PDF,page=page_no,bbox=rule.locator.bbox,source=f"PDF page {page_no} bbox",excerpt=raw),errors=errors))
    doc.close()
    blocked = any(x.status in {"MISSING","CONFLICT"} for x in results)
    return ExtractResponse(sha256=digest,pageCount=len(pages),status="BLOCKED" if blocked else "VALID",fields=results)

