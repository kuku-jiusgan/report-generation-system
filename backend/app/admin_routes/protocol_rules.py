"""方案规则元数据、已上传文件列表和只读试提取。"""
import logging
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.protocol_extractor import extract_protocol
from ..services.protocol_rules import (
    PROTOCOL_INPUTS,
    PROTOCOL_MODES,
    PROTOCOL_TRANSFORM_GROUPS,
    PROTOCOL_TRANSFORMS,
    validate_protocol_rule,
)
from ..services.system_field_groups import list_system_field_groups

logger = logging.getLogger(__name__)


def _preview_inputs(database, field: dict, rule: dict, groups: list[dict], item: dict):
    if rule['config'].get('mode') != 'TABLE_ROWS':
        return [field], [rule], groups
    groups = deepcopy(groups)
    group = next((group for group in groups if group['groupCode'] == rule['config'].get('groupCode')), None)
    if group is None:
        raise ValueError('请选择有效的方案编组')
    if 'sourceMappings' in item:
        mappings = item['sourceMappings']
        if not isinstance(mappings, list) or not all(isinstance(mapping, dict) and mapping.get('sourceType') == 'PROTOCOL' for mapping in mappings):
            raise ValueError('方案试提取的来源映射必须是方案配置数组')
        group['sourceMappings'] = [mapping for mapping in group['sourceMappings'] if mapping.get('sourceType') != 'PROTOCOL'] + mappings
    validate_protocol_rule(field, rule['config'], groups, str(rule.get('transform') or 'TRIM'))
    mapping = next(mapping for mapping in group['sourceMappings'] if mapping['sourceType'] == 'PROTOCOL')
    parent_code = (mapping.get('rowExpansion') or {}).get('parentFieldCode')
    if not parent_code or parent_code == field['fieldCode']:
        return [field], [rule], groups
    parent = database.get_lims_field(parent_code)
    if not parent or not parent.get('enabled', True):
        raise ValueError('方案编组的父记录分组键字段不存在或已停用')
    candidates = [candidate for candidate in database.list_system_field_rules(parent_code)
                  if candidate.get('enabled', True)]
    if (len(candidates) != 1 or candidates[0].get('sourceType') != 'PROTOCOL'
            or candidates[0].get('config', {}).get('mode') != 'TABLE_ROWS'
            or candidates[0]['config'].get('groupCode') != group['groupCode']):
        raise ValueError('方案父记录分组键必须启用同一编组的方案表格明细规则')
    return [parent, field], [candidates[0], rule], groups



def register_protocol_rule_routes(router: APIRouter, repository, settings) -> None:
    @router.get('/protocol-rule-metadata')
    def protocol_metadata() -> dict[str, Any]:
        return {'sourceType': 'PROTOCOL', 'sourceLabel': '方案提取', 'modes': PROTOCOL_MODES,
                'inputs': PROTOCOL_INPUTS, 'transforms': PROTOCOL_TRANSFORMS,
                'transformGroups': PROTOCOL_TRANSFORM_GROUPS,
                'documents': [{'id': source['id'], 'fileName': source['file_name']}
                              for source in repository.database.list_sources() if source['source_type'] == 'PROTOCOL']}

    @router.post('/protocol-rules/preview')
    def preview_protocol_rule(item: dict[str, Any]) -> dict[str, Any]:
        field = repository.database.get_lims_field(str(item.get('fieldCode') or ''))
        if not field or not field.get('enabled', True):
            raise HTTPException(422, '请选择已启用的标准字段')
        source = repository.database.get_source(str(item.get('documentId') or ''))
        if not source or source.get('source_type') != 'PROTOCOL':
            raise HTTPException(422, '请选择已上传的 DOCX 方案')
        config = item.get('config')
        if not isinstance(config, dict):
            raise HTTPException(422, '方案规则配置必须是对象')
        try:
            groups = list_system_field_groups(repository.database)
            fields, rules, groups = _preview_inputs(repository.database, field,
                {'fieldCode': field['fieldCode'], 'name': '试提取', 'sourceType': 'PROTOCOL',
                 'transform': item.get('transform', 'TRIM'), 'config': config}, groups, item)
            validate_protocol_rule(field, config, groups, str(item.get('transform') or 'TRIM'))
            payload = extract_protocol(settings.uploads_dir / source['stored_name'], source['id'], fields,
                rules, groups,
                settings.max_upload_mb * 1024 * 1024, strict=False)
            return {**payload['_meta'], 'groups': {key: value for key, value in payload.items()
                    if key != '_meta' and config.get('mode') == 'TABLE_ROWS'}}
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except Exception as error:
            logger.exception('方案试提取失败 source_id=%s field=%s', source['id'], field['fieldCode'])
            raise HTTPException(422, '方案试提取失败，请检查文件内容或联系管理员') from error
