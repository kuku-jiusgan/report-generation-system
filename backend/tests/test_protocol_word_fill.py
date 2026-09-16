"""方案解析结果经现有 Word 渲染与 AI 上下文读取，不能污染其他来源。"""
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
import pytest

from backend.app.services.ai_report_context import report_ai_context
from backend.app.services.docx_field_values import set_control_text
from backend.app.services.mapped_docx_generator import build_mapped_docx
from backend.app.services.protocol_report_source import replace_protocol_result
from backend.app.services.standard_payloads import standard_context_payload

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W_NS}


def source_payload(values, group='purpose'):
    result = {group: values, '_meta': {'fields': {}, 'warnings': [], 'errors': []}}
    for key in values[0] if isinstance(values, list) else values:
        code = f'{group}.{key}'
        path = f'$.{group}[*].{key}' if isinstance(values, list) else f'$.{group}.{key}'
        result['_meta']['fields'][code] = {'status': 'SUCCESS',
            'value': [record[key] for record in values] if isinstance(values, list) else values[key],
            'source': {'type': 'PROTOCOL', 'sourcePath': path, 'document_id': 'doc-1'}}
    return result


def control(tag, placeholder='模板示例'):
    return f'<w:sdt><w:sdtPr><w:tag w:val="{tag}"/></w:sdtPr><w:sdtContent><w:p><w:r><w:t>{placeholder}</w:t></w:r></w:p></w:sdtContent></w:sdt>'


def generate(tmp_path, body, mappings, data, table_rules=None):
    template, output = tmp_path / 'template.docx', tmp_path / 'out.docx'
    with ZipFile(template, 'w') as archive:
        archive.writestr('word/document.xml', f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
    build_mapped_docx(template, output, mappings, data.get('source_payloads', {}).get('EXCEL', {}), data, table_rules)
    with ZipFile(output) as archive:
        return etree.fromstring(archive.read('word/document.xml'))


def test_section_in_word_has_real_line_breaks(tmp_path: Path):
    data = {'source_payloads': {'EXCEL': {'purpose': {'text': '旧内容'}}}}
    replace_protocol_result(data, source_payload({'text': '第一段。\n第二段。'}), 'hash')
    mapping = {'fieldCode': 'purpose.text', 'standardFieldCode': 'purpose.text', 'sourcePath': '$.purpose.text',
               'sourceType': 'SYSTEM', 'controlTag': 'purpose', 'enabled': True}
    root = generate(tmp_path, control('purpose'), [mapping], data)
    assert root.xpath('.//w:sdt//w:t/text()', namespaces=NS) == ['第一段。', '第二段。']
    assert len(root.xpath('.//w:sdt//w:br', namespaces=NS)) == 1
    assert data['source_payloads']['EXCEL']['purpose']['text'] == '旧内容'


def test_optional_missing_scalar_clears_template_placeholder(tmp_path):
    data = {'source_payloads': {'EXCEL': {'purpose': {'text': '旧内容'}}}}
    payload = {'_meta': {'fields': {'purpose.text': {'status': 'ERROR', 'message': '未匹配',
        'source': {'type': 'PROTOCOL', 'sourcePath': '$.purpose.text'}}}, 'warnings': ['未匹配'], 'errors': []}}
    replace_protocol_result(data, payload, '')
    mapping = {'fieldCode': 'purpose.text', 'standardFieldCode': 'purpose.text', 'sourcePath': '$.purpose.text', 'controlTag': 'purpose'}
    root = generate(tmp_path, control('purpose'), [mapping], data)
    assert not root.xpath('.//w:sdt//w:t/text()', namespaces=NS)


def test_protocol_repeat_rows_fill_from_protocol_namespace(tmp_path):
    data = {'source_payloads': {'EXCEL': {'instruments': [{'name': '错误旧仪器', 'model': '旧型号'}]}}}
    records = [{'name': '仪器甲', 'model': 'A'}, {'name': '仪器乙', 'model': 'B'}]
    replace_protocol_result(data, source_payload(records, 'instruments'), 'hash')
    mappings = [{'fieldCode': f'instruments.{key}', 'standardFieldCode': f'instruments.{key}',
        'sourcePath': f'$.instruments[*].{key}', 'groupItemPath': '$.instruments[*]',
        'controlTag': key, 'repeatType': 'ROW', 'tableNo': 'T1', 'sourceType': 'SYSTEM', 'enabled': True}
        for key in ('name', 'model')]
    body = f'<w:tbl><w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid><w:tr><w:tc>{control("name")}</w:tc><w:tc>{control("model")}</w:tc></w:tr></w:tbl>'
    rules = [{'tableNo': 'T1', 'mode': 'ROW_REPEAT', 'enabled': True, 'physicalTableIndex': 1, 'dataRowStart': 1}]
    root = generate(tmp_path, body, mappings, data, rules)
    assert root.xpath('.//w:tbl/w:tr//w:t/text()', namespaces=NS) == ['仪器甲', 'A', '仪器乙', 'B']


def test_generated_snapshot_ai_group_reads_protocol_and_remains_immutable():
    data = {'source_payloads': {'EXCEL': {'instruments': [{'name': '旧仪器'}]}}}
    replace_protocol_result(data, source_payload([{'name': '仪器甲'}, {'name': '仪器乙'}], 'instruments'), 'hash')
    generation = {'generation_snapshot': {'resolved_data': data, 'original_values': data['original_values']}}
    before = deepcopy(generation)
    context = report_ai_context(generation, {'contextVariables': [{'groupCode': 'instruments', 'valueMode': 'ALL'}]})
    assert context['values']['instruments'] == [{'name': '仪器甲'}, {'name': '仪器乙'}]
    assert generation == before


def test_missing_protocol_group_does_not_read_old_group():
    data = {'source_payloads': {'EXCEL': {'purpose': {'text': '旧内容'}}, 'PROTOCOL': {'_meta': {'fields': {
        'purpose.text': {'status': 'ERROR', 'source': {'sourcePath': '$.purpose.text'}}}}}}}
    assert 'purpose' not in standard_context_payload(data)


def test_replacing_multiline_control_does_not_leave_stale_breaks():
    root = etree.fromstring(f'<w:document xmlns:w="{W_NS}">{control("purpose")}</w:document>')
    target = root[0]
    set_control_text(target, '第一段\n第二段')
    set_control_text(target, '新的单段')
    assert not root.xpath('.//w:br', namespaces=NS)
    assert ''.join(root.xpath('.//w:t/text()', namespaces=NS)) == '新的单段'


@pytest.mark.parametrize('reverse', [False, True])
def test_nested_protocol_group_renders_with_unrelated_mapping_first(tmp_path, reverse):
    records = [{'item': '项目甲', 'details': [{'criteria': '标准甲'}]},
               {'item': '项目乙', 'details': [{'criteria': '标准乙'}]}]
    data = {'source_payloads': {'EXCEL': {'other': [], 'summary': []}}}
    replace_protocol_result(data, source_payload(records, 'summary'), 'hash')
    mappings = [{'fieldCode': 'other.text', 'standardFieldCode': 'other.text',
        'sourcePath': '$.other[*].text', 'groupItemPath': '$.summary[*]',
        'controlTag': 'conclusion', 'repeatType': 'ROW', 'tableNo': 'T1', 'sourceType': 'EXCEL'}]
    target_mappings = [{'fieldCode': f'summary.{key}', 'standardFieldCode': f'summary.{key}',
        'sourcePath': f'$.summary[*].{path}', 'groupItemPath': '$.summary[*]',
        'controlTag': key, 'repeatType': 'ROW', 'tableNo': 'T1', 'sourceType': 'SYSTEM'}
        for key, path in [('item', 'item'), ('criteria', 'details[*].criteria')]]
    mappings.extend(reversed(target_mappings) if reverse else target_mappings)
    body = f'<w:tbl><w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid><w:tr><w:tc>{control("item")}</w:tc><w:tc>{control("criteria")}</w:tc><w:tc>{control("conclusion")}</w:tc></w:tr></w:tbl>'
    rules = [{'tableNo': 'T1', 'mode': 'ROW_REPEAT', 'enabled': True, 'physicalTableIndex': 1, 'dataRowStart': 1}]
    root = generate(tmp_path, body, mappings, data, rules)
    assert root.xpath('.//w:sdt[w:sdtPr/w:tag/@w:val="item"]//w:t/text()', namespaces=NS) == ['项目甲', '项目乙']
    assert root.xpath('.//w:sdt[w:sdtPr/w:tag/@w:val="criteria"]//w:t/text()', namespaces=NS) == ['标准甲', '标准乙']
    assert data['source_payloads']['EXCEL']['summary'] == []
