from typing import Any
from fastapi import APIRouter, HTTPException
from ..services.rule_admin import RuleAdminRepository
from ..services.lims_normalizer import merge_instances

def register_data_source_routes(router: APIRouter, repository: RuleAdminRepository) -> None:
    @router.get('/data-sources')
    def list_data_sources() -> list[dict[str, Any]]: return repository.list_data_sources()
    @router.post('/lims-recognition-test')
    def test_lims_recognition(item: dict[str, Any]) -> dict[str, Any]:
        imported = repository.database.get_lims_import(str(item.get('importId') or ''))
        if not imported: raise HTTPException(404, 'LIMS 导入记录不存在')
        ids = [str(value) for value in item.get('instanceIds', []) if value]
        if not ids: raise HTTPException(422, '至少选择一个实验记录')
        try:
            return merge_instances([repository.database.get_lims_normalized_payload(imported['id'], value) for value in ids], normalized=True)
        except (KeyError, ValueError) as error: raise HTTPException(422, str(error)) from error
    @router.put('/data-sources/{code}')
    def update_data_source(code: str, item: dict[str, Any]) -> dict[str, Any]:
        item['code'] = code; return repository.upsert_data_source(item)
    @router.get('/ai-rules')
    def list_ai_rules() -> list[dict[str, Any]]: return repository.list_ai_rules()
    @router.post('/ai-rules')
    def create_ai_rule(item: dict[str, Any]) -> dict[str, Any]:
        result = repository.upsert_ai_rule(item); repository.save_active_workspace(); return result
    @router.put('/ai-rules/{field_code:path}')
    def update_ai_rule(field_code: str, item: dict[str, Any]) -> dict[str, Any]:
        item['fieldCode'] = field_code; result = repository.upsert_ai_rule(item); repository.save_active_workspace(); return result
    @router.delete('/ai-rules/{rule_id}')
    def delete_ai_rule(rule_id: int) -> dict[str, bool]:
        if not repository.delete_ai_rule(rule_id): raise HTTPException(404, 'AI规则不存在')
        repository.save_active_workspace(); return {'deleted': True}
    @router.post('/ai-rules/test')
    def test_ai_rule(item: dict[str, Any]) -> dict[str, Any]:
        inputs = item.get('sampleInputs', {})
        missing = [field for field in item.get('inputFields', []) if field not in inputs]
        if missing: return {'success': False, 'missingInputs': missing, 'output': '', 'citations': []}
        facts = '；'.join(f'{key}={value}' for key, value in inputs.items())
        return {'success': True, 'mock': True, 'output': f'[AI提供方尚未配置] 已接收结构化事实：{facts}',
                'citations': list(inputs), 'message': '当前仅验证输入、提示词和输出约束；配置模型提供方后执行真实生成。'}
