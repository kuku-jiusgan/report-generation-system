import re
from copy import deepcopy
from typing import Any


UNIT_TYPES = ["Sample", "Standard", "Equipment", "Chromatogram", "Reagent", "Weighing"]
RECORD_MODES = [
    {"value": "ROWS", "label": "按数据行"},
    {"value": "COLUMNS", "label": "按数据列"},
    {"value": "MATRIX", "label": "矩阵单元格"},
]
LIMS_TRANSFORMS = [
    {"value": "TRIM", "label": "去除首尾空白"},
    {"value": "NUMBER", "label": "转换为数值"},
    {"value": "DATE", "label": "转换为日期"},
    {"value": "UPPER", "label": "转为大写"},
    {"value": "LOWER", "label": "转为小写"},
    {"value": "REGEX_REPLACE", "label": "正则替换"},
]


def _field(key: str, label: str, kind: str = "text", **options: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "kind": kind, **options}


def _group(columns: int, fields: list[dict[str, Any]], **options: Any) -> dict[str, Any]:
    return {"columns": columns, "fields": fields, **options}


COMMON_TABLE_GROUPS = [
    _group(2, [
        _field("sectionPattern", "章节路径正则", validation="regex"),
        _field("headerPattern", "表头特征正则", validation="regex"),
    ]),
    _group(3, [
        _field("recordMode", "记录方向", "select", options=RECORD_MODES),
        _field("headerRows", "表头行数", "integer", min=0),
        _field("valuePattern", "取值正则", validation="regex"),
    ]),
    _group(3, [
        _field("dataStartRow", "数据起始行", "integer", min=0),
        _field("rowStride", "行步长", "integer", min=1),
        _field("sourceColumnIndex", "取值列序号", "integer"),
    ], when={"key": "recordMode", "value": "ROWS"}),
    _group(1, [
        _field("sourcePath", "取值列标题正则", validation="regex"),
    ], when={"key": "recordMode", "value": "ROWS"}),
    _group(2, [
        _field("rowPattern", "数据行过滤正则", validation="regex"),
        _field("excludeRowPattern", "数据行排除正则", validation="regex"),
    ], when={"key": "recordMode", "value": "ROWS"}),
    _group(3, [
        _field("dataStartColumn", "数据起始列", "integer", min=0),
        _field("columnStride", "列步长", "integer", min=1),
        _field("rowLabelColumn", "行标题列", "integer"),
    ], when={"key": "recordMode", "value": "COLUMNS"}),
    _group(2, [
        _field("sourceRowIndex", "取值行序号", "integer", min=0),
        _field("sourcePath", "取值行标题正则", validation="regex"),
    ], when={"key": "recordMode", "value": "COLUMNS"}),
    _group(1, [
        _field("columnPattern", "数据列过滤正则", validation="regex"),
    ], when={"key": "recordMode", "value": "COLUMNS"}),
    _group(4, [
        _field("dataStartRow", "数据起始行", "integer", min=0),
        _field("dataStartColumn", "数据起始列", "integer", min=0),
        _field("rowStride", "行步长", "integer", min=1),
        _field("columnStride", "列步长", "integer", min=1),
    ], when={"key": "recordMode", "value": "MATRIX"}),
    _group(3, [
        _field("valueRowIndex", "固定取值行", "integer", min=0),
        _field("valueColumnIndex", "固定取值列", "integer"),
        _field("columnPattern", "列标题过滤正则", validation="regex"),
    ], when={"key": "recordMode", "value": "MATRIX"}),
    _group(4, [
        _field("valueRowOffset", "取值行偏移", "integer"),
        _field("valueColumnOffset", "取值列偏移", "integer"),
        _field("rowPattern", "数据行过滤正则", validation="regex"),
        _field("excludeRowPattern", "数据行排除正则", validation="regex"),
    ], when={"key": "recordMode", "value": "MATRIX"}),
    _group(2, [
        _field("valueTemplate", "取值模板", placeholder="例如 {header}-{value}"),
        _field("headerValuePattern", "列标题取值正则", validation="regex"),
    ]),
]

EXTRACTION_TYPES = [
    {
        "value": "INSTANCE_PATH", "label": "实验实例字段",
        "defaultConfig": {"extractionType": "INSTANCE_PATH", "sourcePath": ""},
        "groups": [_group(1, [
            _field("sourcePath", "实例字段路径", placeholder="例如 projectId 或 auditEvents[*].name"),
        ])],
    },
    {
        "value": "RAW_UNIT_FIELD", "label": "原始 UNITBODY 字段",
        "defaultConfig": {"extractionType": "RAW_UNIT_FIELD", "sourceUnitType": "", "sourcePath": ""},
        "groups": [
            _group(2, [
                _field("sourceUnitType", "LIMS TYPE", "select", options=UNIT_TYPES, allowCustom=True),
                _field("sourcePath", "首选字段路径", placeholder="例如 ext$.mtlname"),
            ]),
            _group(1, [_field("sourcePaths", "候选字段路径", "tags")]),
        ],
    },
    {
        "value": "RICH_TEXT_REGEX", "label": "富文本正文",
        "defaultConfig": {"extractionType": "RICH_TEXT_REGEX"},
        "groups": [_group(2, [
            _field("sectionPattern", "章节路径正则", validation="regex"),
            _field("valuePattern", "取值正则", validation="regex"),
        ])],
    },
    {
        "value": "HTML_TABLE_COLUMN", "label": "HTML 表格",
        "defaultConfig": {"extractionType": "HTML_TABLE_COLUMN", "recordMode": "ROWS", "headerRows": 1},
        "groups": COMMON_TABLE_GROUPS,
    },
]
DIRECT_TYPES = frozenset(item["value"] for item in EXTRACTION_TYPES)
TRANSFORM_GROUPS = [
    _group(2, [
        _field("replacePattern", "替换正则", "textarea", rows=2, validation="regex",
               placeholder="例如 (?:\\([^()（）]*=[^()（）]*\\)|（[^()（）]*=[^()（）]*）)"),
        _field("replaceWith", "替换为", placeholder="留空表示删除匹配内容"),
    ], when={"key": "transform", "value": "REGEX_REPLACE"}),
]


def lims_rule_metadata() -> dict[str, Any]:
    return deepcopy({
        "sourceType": "LIMS", "extractionTypes": EXTRACTION_TYPES,
        "transforms": LIMS_TRANSFORMS, "transformGroups": TRANSFORM_GROUPS,
    })


def _active_fields(extraction_type: str, config: dict[str, Any], transform: str) -> list[dict[str, Any]]:
    definition = next(item for item in EXTRACTION_TYPES if item["value"] == extraction_type)
    groups = list(definition["groups"]) + TRANSFORM_GROUPS
    active = []
    for group in groups:
        condition = group.get("when")
        condition_value = transform if condition and condition["key"] == "transform" else config.get(
            condition["key"] if condition else "",
        )
        if not condition or condition_value == condition["value"]:
            active.extend(group["fields"])
    return active


def validate_lims_rule_config(config: dict[str, Any], transform: str) -> dict[str, Any]:
    normalized = dict(config)
    validation_context = normalized
    extraction_type = str(normalized.get("extractionType") or "").upper()
    if extraction_type not in DIRECT_TYPES:
        raise ValueError("LIMS 提取方式必须直接读取实例字段、原始 UNITBODY、富文本或 HTML 表格")
    normalized["extractionType"] = extraction_type
    if extraction_type in {"INSTANCE_PATH", "RAW_UNIT_FIELD"}:
        if not str(normalized.get("sourcePath") or "").strip() and not normalized.get("sourcePaths"):
            raise ValueError("LIMS 直接字段提取必须配置原始字段路径")
    if extraction_type == "RAW_UNIT_FIELD" and not normalized.get("sourceUnitType"):
        raise ValueError("原始 UNITBODY 字段提取必须配置 LIMS TYPE")
    if extraction_type == "HTML_TABLE_COLUMN":
        record_mode = str(normalized.get("recordMode") or "ROWS").upper()
        if record_mode not in {item["value"] for item in RECORD_MODES}:
            raise ValueError("HTML 表格记录方向只能是 ROWS、COLUMNS 或 MATRIX")
        validation_context = {**normalized, "recordMode": record_mode}
        source_path = str(normalized.get("sourcePath") or "").strip()
        if record_mode == "ROWS" and not source_path and normalized.get("sourceColumnIndex") in (None, ""):
            raise ValueError("按数据行提取必须配置取值列标题正则或取值列序号")
        if record_mode == "COLUMNS" and not source_path and normalized.get("sourceRowIndex") in (None, ""):
            raise ValueError("按数据列提取必须配置取值行标题正则或取值行序号")
    normalized_transform = transform.upper()
    descriptors = {
        field["key"]: field
        for field in _active_fields(extraction_type, validation_context, normalized_transform)
    }
    for key, descriptor in descriptors.items():
        value = normalized.get(key)
        if value in (None, ""):
            continue
        if descriptor["kind"] == "integer":
            try:
                number = int(value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"{key} 必须是整数") from error
            if "min" in descriptor and number < descriptor["min"]:
                raise ValueError(f"{key} 不能小于 {descriptor['min']}")
            normalized[key] = number
        if descriptor.get("validation") == "regex":
            try:
                re.compile(str(value))
            except re.error as error:
                raise ValueError(f"{key} 正则无效：{error}") from error
    if normalized_transform == "REGEX_REPLACE" and not str(normalized.get("replacePattern") or ""):
        raise ValueError("正则替换必须配置替换正则")
    return normalized
