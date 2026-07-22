import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable
from .models import ExtractionRule, FieldResult, Evidence, SourceType

def normalize(raw: str, rule: ExtractionRule) -> tuple[str, list[str]]:
    value = raw.strip() if rule.transformer.trim else raw
    value = rule.transformer.enum.get(value, value)
    errors: list[str] = []
    if rule.transformer.unit_pattern:
        value = re.sub(rule.transformer.unit_pattern, "", value).strip()
    if rule.transformer.decimals is not None:
        try:
            number = Decimal(value.replace(",", ""))
            quantum = Decimal(1).scaleb(-rule.transformer.decimals)
            value = str(number.quantize(quantum, rounding=ROUND_HALF_UP))
        except InvalidOperation:
            errors.append("数值格式无效")
    v = rule.validator
    if v.pattern and not re.fullmatch(v.pattern, value): errors.append("格式校验失败")
    if v.minimum is not None or v.maximum is not None:
        try:
            number = float(value)
            if v.minimum is not None and number < v.minimum: errors.append(f"小于最小值 {v.minimum}")
            if v.maximum is not None and number > v.maximum: errors.append(f"大于最大值 {v.maximum}")
        except ValueError: errors.append("范围校验要求数值")
    return value, errors

def missing(rule: ExtractionRule, source: str, page: int | None = None) -> FieldResult:
    status = "MISSING" if rule.onMissing == "BLOCK" else "WARNING"
    return FieldResult(fieldCode=rule.fieldCode,label=rule.label,rawValue=None,normalizedValue=None,status=status,
        targetControlTag=rule.targetControlTag,evidence=Evidence(sourceType=rule.sourceType,page=page,source=source),errors=["未找到匹配值"])

def from_oracle(rule: ExtractionRule, row: dict[str, object]) -> FieldResult:
    column = (rule.locator.column or "").upper()
    normalized_row = {str(k).upper(): v for k, v in row.items()}
    raw = normalized_row.get(column)
    if raw is None or str(raw).strip() == "": return missing(rule, f"Oracle:{column}")
    value, errors = normalize(str(raw), rule)
    return FieldResult(fieldCode=rule.fieldCode,label=rule.label,rawValue=str(raw),normalizedValue=value,status="WARNING" if errors else "VALID",
        targetControlTag=rule.targetControlTag,evidence=Evidence(sourceType=SourceType.ORACLE,source=f"Oracle:{column}",excerpt=str(raw)),errors=errors)

def find_in_text(rule: ExtractionRule, pages: Iterable[tuple[int, str]]) -> FieldResult:
    last_page = rule.locator.page_from
    for page, text in pages:
        last_page = page
        if page < rule.locator.page_from or (rule.locator.page_to and page > rule.locator.page_to): continue
        area = text
        if rule.locator.anchor:
            anchor_at = text.lower().find(rule.locator.anchor.lower())
            if anchor_at < 0: continue
            area = text[anchor_at:anchor_at + 1200]
        match = re.search(rule.locator.pattern or "", area, flags=re.IGNORECASE | re.MULTILINE)
        if not match: continue
        raw = match.group(1) if match.groups() else match.group(0)
        value, errors = normalize(raw, rule)
        return FieldResult(fieldCode=rule.fieldCode,label=rule.label,rawValue=raw,normalizedValue=value,status="WARNING" if errors else "VALID",
            targetControlTag=rule.targetControlTag,evidence=Evidence(sourceType=SourceType.PDF,page=page,source=f"PDF page {page}",excerpt=area[max(0,match.start()-60):match.end()+60]),errors=errors)
    return missing(rule,"PDF",last_page)

