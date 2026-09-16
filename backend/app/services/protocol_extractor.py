"""按后台规则提取方案字段，结果直接生成标准字段目录载荷。"""
import logging
import re
from pathlib import Path
from typing import Any

from .protocol_row_expansion import group_protocol_values, write_protocol_value
from .protocol_document import validate_protocol_document
from .protocol_rules import validate_protocol_conflicts
from .protocol_structure import read_protocol_structure

logger = logging.getLogger(__name__)


class ProtocolMatchError(ValueError):
    """有效规则没有唯一的原文结果；可选字段允许显式记录此状态。"""


def _unique(items: list, description: str):
    if len(items) != 1:
        raise ProtocolMatchError(f'{description}：未匹配' if not items else f'{description}：匹配到 {len(items)} 处，请收紧定位条件')
    return items[0]


def _scope(blocks: list[dict], config: dict) -> list[dict]:
    pattern = config['sectionPattern']
    starts = [index for index, block in enumerate(blocks) if block['kind'] == 'paragraph'
              and (re.fullmatch(pattern, block['section']) if block['level'] is not None else re.search(pattern, block['text']))]
    start = _unique(starts, '方案章节或起始段落')
    heading = blocks[start]
    end_pattern = config.get('endPattern')
    if end_pattern:
        ends = [index for index in range(start + 1, len(blocks))
                if blocks[index]['kind'] == 'paragraph' and re.search(end_pattern, blocks[index]['text'])]
        end = _unique(ends, '方案结束段落')
    elif heading['level'] is not None:
        end = next((index for index in range(start + 1, len(blocks))
                    if blocks[index]['kind'] == 'paragraph' and blocks[index]['level'] is not None
                    and blocks[index]['level'] <= heading['level']), len(blocks))
    else:
        raise ValueError('方案起始段落没有标题层级，请配置结束段落正则')
    scope = blocks[start:end]
    for block in scope:
        if 'error' in block:
            raise ValueError(f"方案表格 {block['table']}：{block['error']}")
    return scope


def _quote(block: dict, **position) -> dict:
    return {'section': block['section'], **{key: block[key] for key in ('paragraph', 'table') if key in block},
            **position}


def _capture(text: str, pattern: str) -> str:
    matches = list(re.finditer(pattern, text))
    match = _unique(matches, '方案取值正则')
    value = match.group(1) if match.groups() else match.group(0)
    if value is None or not value.strip():
        raise ProtocolMatchError('方案提取结果为空')
    return value


def _table(scope: list[dict], config: dict) -> tuple[dict, int]:
    candidates = [(block, index) for block in scope if block['kind'] == 'table'
                  for index, row in enumerate(block['rows'])
                  if re.search(config['headerPattern'], '\t'.join(row))]
    return _unique(candidates, '方案表格表头')


def _data_rows(block: dict, header: int, config: dict) -> list[tuple[int, list[str]]]:
    rows = [(index + 1, row) for index, row in enumerate(block['rows']) if index > header
            and any(cell.strip() for cell in row)
            and (not config.get('rowPattern') or re.search(config['rowPattern'], '\t'.join(row)))]
    if not rows:
        raise ProtocolMatchError('方案表格没有符合条件的明细行')
    return rows


def _column(block: dict, header: int, pattern: str) -> int:
    return _unique([index for index, cell in enumerate(block['rows'][header]) if re.search(pattern, cell)],
                   '方案取值列')


def _scalar(scope: list[dict], config: dict) -> tuple[str, list[dict]]:
    mode = config['mode']
    if mode == 'SECTION':
        paragraphs = [block for block in scope[1:] if block['kind'] == 'paragraph']
        if any(block['kind'] == 'table' for block in scope[1:]):
            raise ValueError('方案章节包含表格，请为表格内容配置表格提取规则')
        value = '\n'.join(block['text'] for block in paragraphs)
        locations = [_quote(block, quote=block['text']) for block in paragraphs]
    elif mode == 'LABEL':
        candidates = [(block, match) for block in scope if block['kind'] == 'paragraph'
                      for match in re.finditer(config['labelPattern'], block['text'])]
        block, match = _unique(candidates, '方案标签')
        value = block['text'][match.end():].lstrip(' \t：:')
        locations = [_quote(block, quote=block['text'])]
    else:
        block, header = _table(scope, config)
        rows = _data_rows(block, header, config)
        if mode == 'TABLE_CELL':
            candidates = [(row_number, row, index) for row_number, row in rows
                          for index, cell in enumerate(row) if re.search(config['labelPattern'], cell)]
            row_number, row, column = _unique(candidates, '方案表格标签')
            if column + 1 >= len(row):
                raise ProtocolMatchError('方案表格标签右侧没有单元格')
            column += 1
        else:
            column = _column(block, header, config['columnPattern'])
            row_number, row = _unique(rows, '方案表格单值行')
        value = row[column]
        locations = [_quote(block, row=row_number, column=column + 1, quote=value)]
    if config.get('valuePattern'):
        value = _capture(value, config['valuePattern'])
    if not value.strip():
        raise ProtocolMatchError('方案提取结果为空')
    return value, locations


def _rows(blocks: list[dict], config: dict, field: dict, groups: list[dict], cache: dict):
    code = config['groupCode']
    group = next(item for item in groups if item['groupCode'] == code)
    mapping = next(item for item in group['sourceMappings'] if item['sourceType'] == 'PROTOCOL')
    if code not in cache:
        try:
            block, header = _table(_scope(blocks, mapping), mapping)
            cache[code] = (block, header, _data_rows(block, header, mapping))
        except ProtocolMatchError as error:
            cache[code] = error
    if isinstance(cache[code], Exception):
        raise cache[code]
    block, header, rows = cache[code]
    expansion = mapping.get('rowExpansion')
    column_config = next(item for item in mapping['columnMappings'] if item['fieldCode'] == field['fieldCode'])
    column = _column(block, header, column_config['columnPattern'])
    values, locations = [], []
    for number, row in rows:
        value = row[column]
        if not value.strip():
            raise ProtocolMatchError(f'方案表格第 {number} 行、第 {column + 1} 列为空')
        values.append(value)
        locations.append(_quote(block, row=number, column=column + 1, quote=value))
    if expansion:
        parent_config = next(item for item in mapping['columnMappings']
                             if item['fieldCode'] == expansion['parentFieldCode'])
        parent_column = _column(block, header, parent_config['columnPattern'])
        return group_protocol_values([row[parent_column] for _, row in rows], values, locations,
                                     field['legacyJsonPath'].count('[*]') == 2,
                                     expansion['parentFieldCode'])
    return values, locations


def extract_protocol(path: Path | None, document_id: str, fields: list[dict], rules: list[dict],
                     groups: list[dict], max_bytes: int, strict: bool = True) -> dict[str, Any]:
    validate_protocol_conflicts(fields, rules, groups)
    selected = [rule for rule in rules if rule.get('enabled', True) and rule.get('sourceType') == 'PROTOCOL']
    if path is not None and selected:
        validate_protocol_document(path, max_bytes)
        blocks = read_protocol_structure(path)
    else:
        blocks = []
    payload: dict[str, Any] = {}
    meta: dict[str, Any] = {'fields': {}, 'warnings': [], 'errors': []}
    by_code = {field['fieldCode']: field for field in fields}
    cache: dict[str, Any] = {}
    for rule in selected:
        code, config = rule['fieldCode'], rule['config']
        field = by_code[code]
        source = {'type': 'PROTOCOL', 'document_id': document_id, 'ruleId': rule.get('id'),
                  'ruleName': rule.get('name', ''), 'sourcePath': field['legacyJsonPath']}
        try:
            if path is None:
                raise ProtocolMatchError('未上传 Word 方案，请上传 DOCX 文件')
            if config['mode'] == 'TABLE_ROWS':
                value, locations = _rows(blocks, config, field, groups, cache)
            else:
                value, locations = _scalar(_scope(blocks, config), config)
            value = _transform(value, rule.get('transform', 'TRIM'))
            _validate_value(value, field)
            write_protocol_value(payload, field['legacyJsonPath'], value)
            meta['fields'][code] = {'status': 'SUCCESS', 'value': value, 'source': {**source, 'locations': locations}}
        except ProtocolMatchError as error:
            message = f"方案字段「{field.get('label', code)}」：{error}"
            meta['fields'][code] = {'status': 'ERROR', 'message': message, 'source': source}
            meta['errors' if config.get('required', True) else 'warnings'].append(message)
        logger.info('方案字段提取 field=%s rule_id=%s status=%s', code, rule.get('id'), meta['fields'][code]['status'])
    for rule in selected:
        if rule['config']['mode'] == 'TABLE_ROWS':
            payload.setdefault(rule['config']['groupCode'], [])
    payload['_meta'] = meta
    if strict and meta['errors']:
        raise ValueError('；'.join(meta['errors']))
    return payload


def _transform(value: Any, transform: str) -> Any:
    if isinstance(value, list):
        return [_transform(item, transform) for item in value]
    if transform == 'TRIM':
        return value.strip()
    if transform == 'UPPER':
        return value.upper()
    if transform == 'LOWER':
        return value.lower()
    if transform == 'NUMBER':
        try:
            from decimal import Decimal, InvalidOperation
            result = Decimal(value.strip())
            if not result.is_finite():
                raise InvalidOperation
            return str(result)
        except InvalidOperation as error:
            raise ProtocolMatchError('方案取值不能转换为数值') from error
    if transform == 'DATE':
        from datetime import date
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError as error:
            raise ProtocolMatchError('方案日期必须为 YYYY-MM-DD 格式') from error
    raise ValueError(f'不支持的方案结果转换：{transform}')


def _validate_value(value: Any, field: dict) -> None:
    from datetime import date
    from decimal import Decimal, InvalidOperation
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, list):
            _validate_value(item, field)
            continue
        pattern = field.get('validationRegex')
        if pattern and not re.fullmatch(pattern, str(item)):
            raise ProtocolMatchError('方案取值不符合字段校验正则')
        try:
            if field['dataType'] == 'decimal' and not Decimal(str(item)).is_finite():
                raise InvalidOperation
            if field['dataType'] == 'date':
                date.fromisoformat(str(item))
            if field['dataType'] == 'boolean' and str(item) not in {'true', 'false'}:
                raise ValueError
        except (ValueError, InvalidOperation) as error:
            raise ProtocolMatchError(f"方案取值不符合字段数据类型 {field['dataType']}") from error
