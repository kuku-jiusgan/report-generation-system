"""方案表格按显式父记录键分组，保留每个项目的原文明细行。"""
from copy import deepcopy
import re

from .payload_paths import set_payload_path


def validate_row_expansion(mapping: dict, group: dict, fields: list[dict]) -> None:
    expansion = mapping.get('rowExpansion')
    if expansion is None:
        return
    if not isinstance(expansion, dict) or expansion.get('valueScope') != 'PER_PARENT_ROW':
        raise ValueError('方案明细必须显式配置按主表父记录键分组')
    level = expansion.get('levelKey')
    if not isinstance(level, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', level):
        raise ValueError('方案明细展开必须配置有效的数组层键名')
    parent = expansion.get('parentFieldCode')
    parent_field = next((field for field in fields if field.get('fieldCode') == parent), None)
    if parent_field is None:
        raise ValueError('方案父记录分组键必须属于当前编组')
    if (parent_field.get('levelKey') or '[*]' in parent_field.get('fieldPath', '')
            or str(parent_field.get('legacyJsonPath', '')).count('[*]') > 1):
        raise ValueError('方案父记录分组键必须位于记录顶层')
    if not any(column.get('fieldCode') == parent for column in mapping.get('columnMappings', [])):
        raise ValueError('方案父记录分组键必须配置主表列映射')
    levels = group.get('levels')
    if levels is not None and not any(item['levelKey'] == level and item['kind'] == 'ARRAY' for item in levels):
        raise ValueError('方案明细展开引用的数组层不存在')


def validate_expanded_path(field: dict, group: dict, mapping: dict) -> None:
    path = field['legacyJsonPath']
    expansion = mapping.get('rowExpansion')
    if not expansion:
        if path.count('[*]') != 1:
            raise ValueError('方案表格多层数组必须配置明细展开清单，不能猜测分组边界')
        return
    prefix = f"$.{group['groupCode']}[*].{expansion['levelKey']}[*]."
    if path.count('[*]') > 1 and not path.startswith(prefix):
        raise ValueError('方案字段路径与配置的明细展开数组层不一致')
    if path.count('[*]') > 2:
        raise ValueError('方案明细展开只支持父记录和一个明细数组层')
    if field['fieldCode'] == expansion['parentFieldCode'] and path.count('[*]') != 1:
        raise ValueError('方案父记录分组键必须位于记录顶层')


def group_protocol_values(parents: list[str], values: list, locations: list[dict],
                          nested: bool, parent_field_code: str) -> tuple[list, list[dict]]:
    if not (len(parents) == len(values) == len(locations)):
        raise ValueError('方案分组键、字段值与原文位置数量不一致')
    grouped: dict[str, list] = {}
    quoted = []
    for parent, value, location in zip(parents, values, locations):
        key = parent.strip()
        if not key:
            raise ValueError('方案主表的父记录分组键不能为空')
        grouped.setdefault(key, []).append(value)
        quoted.append({**location, 'parentFieldCode': parent_field_code, 'parentValue': key})
    if nested:
        return list(grouped.values()), quoted
    result = []
    for items in grouped.values():
        if len({value.strip() for value in items}) != 1:
            raise ValueError('同一方案父记录的顶层字段存在冲突，请检查主表数据')
        result.append(items[0])
    return result, quoted


def write_protocol_value(payload: dict, path: str, value) -> None:
    """嵌套值已经按父记录组织；禁止调用扁平值平均分组通路。"""
    if path.count('[*]') < 2:
        set_payload_path(payload, path, value)
        return
    if not isinstance(value, list) or not all(isinstance(items, list) for items in value):
        raise ValueError('方案多层数组写入必须提供明确的父子分组值')
    prefix, tail = path.removeprefix('$.').split('[*].', 1)
    if '.' in prefix:
        raise ValueError('方案父记录必须使用编组编码作为顶层数组')
    replacement = deepcopy(payload)
    records = replacement.setdefault(prefix, [{} for _ in value])
    if not isinstance(records, list) or len(records) != len(value):
        raise ValueError('方案字段父记录数量不一致')
    for record, children in zip(records, value):
        if not isinstance(record, dict):
            raise ValueError('方案父记录必须是对象')
        child_key = tail.split('[*].', 1)[0]
        existing = record.get(child_key)
        if existing is not None and (not isinstance(existing, list) or len(existing) != len(children)):
            raise ValueError('方案字段明细记录数量不一致')
        set_payload_path(record, '$.' + tail, children)
    payload.clear()
    payload.update(replacement)
