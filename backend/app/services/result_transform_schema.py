"""字段提取结果转换的共享元数据与配置校验。"""
import re
from typing import Any


RESULT_TRANSFORMS = [
    {"value": "TRIM", "label": "去除首尾空白"},
    {"value": "NUMBER", "label": "转换为数值"},
    {"value": "DATE", "label": "转换为日期"},
    {"value": "UPPER", "label": "转为大写"},
    {"value": "LOWER", "label": "转为小写"},
    {"value": "REGEX_REPLACE", "label": "正则替换"},
]
RESULT_TRANSFORM_GROUPS = [
    {
        "columns": 2,
        "fields": [
            {
                "key": "replacePattern", "label": "替换正则", "kind": "textarea",
                "rows": 2, "validation": "regex",
                "placeholder": "例如 (?:\\([^()（）]*=[^()（）]*\\)|（[^()（）]*=[^()（）]*）)",
            },
            {
                "key": "replaceWith", "label": "替换为", "kind": "text",
                "placeholder": "留空表示删除匹配内容",
            },
        ],
        "when": {"key": "transform", "value": "REGEX_REPLACE"},
    },
]
RESULT_TRANSFORM_VALUES = frozenset(item["value"] for item in RESULT_TRANSFORMS)


def validate_result_transform(config: dict[str, Any], transform: str, source_label: str) -> str:
    normalized = str(transform or "TRIM").upper()
    if normalized not in RESULT_TRANSFORM_VALUES:
        raise ValueError(f"不支持的{source_label}结果转换：{normalized}")
    if normalized != "REGEX_REPLACE":
        return normalized
    pattern = config.get("replacePattern")
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("正则替换必须配置替换正则")
    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError(f"replacePattern 正则无效：{error}") from error
    return normalized
