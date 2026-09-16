"""方案规则的配置校验；预览、保存和正式解析共用。"""
import re
from typing import Any

from .protocol_row_expansion import validate_expanded_path, validate_row_expansion


PROTOCOL_MODES = [
    {'value': 'LABEL', 'label': '正文标签取值', 'inputs': ['sectionPattern', 'endPattern', 'labelPattern', 'valuePattern']},
    {'value': 'SECTION', 'label': '章节正文', 'inputs': ['sectionPattern', 'endPattern', 'valuePattern']},
    {'value': 'TABLE_CELL', 'label': '表格标签右侧单元格', 'inputs': ['sectionPattern', 'endPattern', 'headerPattern', 'labelPattern', 'rowPattern', 'valuePattern']},
    {'value': 'TABLE_COLUMN', 'label': '表格列单值', 'inputs': ['sectionPattern', 'endPattern', 'headerPattern', 'columnPattern', 'rowPattern', 'valuePattern']},
    {'value': 'TABLE_ROWS', 'label': '表格全部明细行', 'inputs': ['groupCode']},
]
PROTOCOL_INPUTS = {
    'sectionPattern': {'label': '章节路径 / 起始段落正则', 'help': '有标题层级时完整匹配标题路径（层级用 / 分隔）；普通段落按正则定位起点。'},
    'endPattern': {'label': '结束段落正则（可选）', 'help': '没有标题层级时必须填写；结束段落不包含在结果中。'},
    'labelPattern': {'label': '标签正则', 'help': '正文取标签后的文字；表格取标签右侧单元格。'},
    'valuePattern': {'label': '取值正则（可选）', 'help': '存在捕获组时取第一组，否则取完整匹配；必须唯一匹配。'},
    'headerPattern': {'label': '表头正则', 'help': '完整表头行以制表符连接，必须唯一匹配。'},
    'columnPattern': {'label': '列标题正则', 'help': '必须唯一匹配一个表头单元格。'},
    'rowPattern': {'label': '明细行过滤正则（可选）', 'help': '在以制表符连接的整行文字中匹配。'},
}

MODES = {item['value'] for item in PROTOCOL_MODES}
PATTERNS = ('sectionPattern', 'endPattern', 'labelPattern', 'valuePattern',
            'headerPattern', 'columnPattern', 'rowPattern')


def validate_protocol_locator(config: dict[str, Any]) -> None:
    for key in PATTERNS:
        pattern = config.get(key, '')
        if not isinstance(pattern, str):
            raise ValueError(f'方案规则 {key} 必须是文本')
        if pattern:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f'方案规则 {key} 正则无效：{error}') from error
    if not str(config.get('sectionPattern') or '').strip():
        raise ValueError('方案规则必须配置章节路径或起始段落正则')


def validate_protocol_rule(field: dict, config: dict, groups: list[dict]) -> None:
    path = field.get('legacyJsonPath')
    if not isinstance(path, str) or not re.fullmatch(r'\$\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?)*', path):
        raise ValueError('方案字段缺少有效的标准 JSON 路径')
    mode = config.get('mode')
    if mode not in MODES:
        raise ValueError('请选择有效的方案提取方式')
    if not isinstance(config.get('required', True), bool):
        raise ValueError('方案规则的必需标记必须是布尔值')
    if field.get('dataType') not in {'string', 'richText', 'decimal', 'date', 'boolean'}:
        raise ValueError('方案提取不支持当前字段的数据类型')
    if mode == 'TABLE_ROWS':
        group = next((item for item in groups if item['groupCode'] == config.get('groupCode')
                      and item.get('enabled', True)), None)
        if not group or group.get('cardinality') != 'MANY':
            raise ValueError('方案表格明细必须引用已启用的多行编组')
        mappings = [item for item in group.get('sourceMappings', []) if item.get('sourceType') == 'PROTOCOL']
        if len(mappings) != 1:
            raise ValueError('方案表格明细编组必须配置且只能配置一条方案来源映射')
        mapping = mappings[0]
        validate_protocol_locator(mapping)
        if not mapping.get('headerPattern'):
            raise ValueError('方案表格明细必须配置表头正则')
        columns = mapping.get('columnMappings', [])
        validate_row_expansion(mapping, group, group.get('fields', [field]))
        if not any(item.get('fieldCode') == field['fieldCode'] for item in columns):
            raise ValueError('当前字段未配置在方案编组列映射中')
        if field.get('collectionCode') != group['groupCode']:
            raise ValueError('方案字段与引用编组的归属不一致')
        validate_expanded_path(field, group, mapping)
        if not str(field.get('legacyJsonPath', '')).startswith(f"$.{group['groupCode']}[*]."):
            raise ValueError('方案表格明细必须使用编组编码作为标准数组路径')
        for column in columns:
            pattern = column.get('columnPattern')
            if not isinstance(pattern, str) or not pattern:
                raise ValueError('方案表格列匹配正则不能为空')
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f'方案表格列正则无效：{error}') from error
        if any(key in config and config[key] for key in PATTERNS):
            raise ValueError('方案表格明细的定位条件必须配置在编组来源映射中')
        return
    validate_protocol_locator(config)
    if '[*]' in str(field.get('legacyJsonPath', '')):
        raise ValueError('多行字段请使用方案表格明细提取方式')
    if mode in {'LABEL', 'TABLE_CELL'} and not config.get('labelPattern'):
        raise ValueError('方案标签取值必须配置标签正则')
    if mode == 'TABLE_COLUMN' and not config.get('columnPattern'):
        raise ValueError('方案表格列取值必须配置列标题正则')
    if mode in {'TABLE_CELL', 'TABLE_COLUMN'} and not config.get('headerPattern'):
        raise ValueError('方案表格取值必须配置表头正则')


def validate_protocol_conflicts(fields: list[dict], rules: list[dict], groups: list[dict]) -> None:
    by_code = {field['fieldCode']: field for field in fields if field.get('enabled', True)}
    seen_paths: dict[str, str] = {}
    enabled = [rule for rule in rules if rule.get('enabled', True)]
    for code in {rule['fieldCode'] for rule in enabled if rule.get('sourceType') == 'PROTOCOL'}:
        candidates = [rule for rule in enabled if rule['fieldCode'] == code]
        if len(candidates) != 1:
            raise ValueError(f'字段 {code} 已配置方案来源，不能同时启用其他取值规则')
        if code not in by_code:
            raise ValueError(f'方案规则引用的字段不存在或已停用：{code}')
        validate_protocol_rule(by_code[code], candidates[0].get('config', {}), groups)
        path = by_code[code]['legacyJsonPath']
        if path in seen_paths:
            raise ValueError(f'方案字段 {code} 与 {seen_paths[path]} 的标准路径重复：{path}')
        seen_paths[path] = code
