"""报告流程接入方案解析；先完成解析再替换旧值，失败不修改报告数据。"""
from copy import deepcopy
from pathlib import Path
from typing import Any

from .protocol_extractor import extract_protocol
from .protocol_document import validate_protocol_document


def protocol_document_path(database, settings, data: dict[str, Any]) -> Path:
    document = data.get('source_payloads', {}).get('PROTOCOL_DOCUMENT')
    if not isinstance(document, dict) or not document.get('id'):
        raise ValueError('报告未关联 Word 方案，请先上传方案文件')
    source = database.get_source(document['id'])
    if not source or source.get('source_type') != 'PROTOCOL':
        raise ValueError('报告关联的方案文件不存在或类型无效')
    path = settings.uploads_dir / source['stored_name']
    if not path.is_file():
        raise ValueError('报告关联的方案原始文件不存在，请重新上传')
    validate_protocol_document(path, settings.max_upload_mb * 1024 * 1024)
    return path


def refresh_protocol_source(database, settings, data: dict[str, Any]) -> None:
    rules = database.list_system_field_rules()
    if not any(rule.get('enabled', True) and rule.get('sourceType') == 'PROTOCOL' for rule in rules):
        if 'PROTOCOL' in data.get('source_payloads', {}):
            replace_protocol_result(data, {'_meta': {'fields': {}, 'warnings': [], 'errors': []}}, '')
        return
    fields = database.list_lims_fields(True)
    from .system_field_groups import list_system_field_groups
    groups = list_system_field_groups(database)
    document = data.get('source_payloads', {}).get('PROTOCOL_DOCUMENT')
    source = None
    if document:
        source = database.get_source(document['id'])
        if not source or source.get('source_type') != 'PROTOCOL':
            raise ValueError('报告关联的方案文件不存在或类型无效')
        path = settings.uploads_dir / source['stored_name']
        if not path.is_file():
            raise ValueError('报告关联的方案原始文件不存在，请重新上传')
    else:
        path = None
    payload = extract_protocol(path, source['id'] if source else '', fields, rules, groups,
                               settings.max_upload_mb * 1024 * 1024, strict=False)
    # 报告运行时允许方案字段缺失；保留字段级 ERROR 详情，同时将整体失败降为可见告警。
    meta = payload['_meta']
    meta['warnings'].extend(meta['errors'])
    meta['errors'] = []
    replace_protocol_result(data, payload, source.get('sha256', '') if source else '')


def replace_protocol_result(data: dict[str, Any], payload: dict, sha256: str) -> None:
    replacement = deepcopy(data)
    old_payload = replacement.setdefault('source_payloads', {}).get('PROTOCOL', {})
    old_meta = old_payload.get('_meta', {})
    old_codes = set(old_meta.get('fields', {}))
    sources = replacement.setdefault('field_sources', {})
    old_codes.update(code for code, detail in sources.items() if detail.get('type') == 'PROTOCOL')
    originals = replacement.setdefault('original_values', {})
    for code in old_codes:
        if sources.get(code, {}).get('type') == 'PROTOCOL':
            sources.pop(code, None)
            originals.pop(code, None)
            replacement.pop(code, None)
    old_messages = old_meta.get('warnings', [])
    replacement['warnings'] = [message for message in replacement.get('warnings', []) if message not in old_messages]
    replacement['warnings'].extend(payload['_meta']['warnings'])
    for code, result in payload['_meta']['fields'].items():
        sources[code] = {**result['source'], 'sha256': sha256, 'status': result['status'],
                         **({'message': result['message']} if 'message' in result else {})}
        if result['status'] == 'SUCCESS':
            originals[code] = result['value']
        else:
            originals.pop(code, None)
    replacement['source_payloads']['PROTOCOL'] = payload
    data.clear()
    data.update(replacement)
