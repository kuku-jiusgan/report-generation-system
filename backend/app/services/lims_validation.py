import hashlib
import re
from typing import Any


VALIDATION_ITEMS = (
    ("系统适用性", "systemSuitability"), ("专属性", "specificity"),
    ("检测限", "lod"), ("定量限", "loq"), ("线性", "linearity"),
    ("重复性", "repeatability"), ("中间精密度", "intermediatePrecision"),
    ("准确度", "accuracy"), ("溶液稳定性", "solutionStability"),
    ("稳定性", "solutionStability"), ("耐用性", "robustness"),
)
VALIDATION_ORDER = tuple(dict.fromkeys(code for _, code in VALIDATION_ITEMS))


def validation_code(value: str, custom: bool = False) -> str | None:
    normalized = re.sub(r"\s+", "", str(value or ""))
    for label, code in VALIDATION_ITEMS:
        if label in normalized:
            return code
    if not custom or not normalized:
        return None
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"custom-{digest}"


def sort_validation_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {code: index for index, code in enumerate(VALIDATION_ORDER)}
    return sorted(records, key=lambda item: (
        order.get(str(item.get("validationItemCode") or ""), len(order)),
        str(item.get("validationItemCode") or ""), str(item.get("field1") or ""),
    ))
