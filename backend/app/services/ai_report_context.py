import logging
from typing import Any

from .ai_field_generator import AiGenerationError, context_variables, needs_per_record_generation, resolve_context_values
from .standard_payloads import standard_context_payload
from .ai_context_inputs import prepare_ai_context


logger = logging.getLogger(__name__)


def report_ai_context(generation: dict[str, Any], config: dict[str, Any],
                      collection_code: str = "", record_index: int | None = None,
                      target_field: dict[str, Any] | None = None,
                      context_fields: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """仅使用不可变生成快照，不读取报告当前值或重新执行提取。"""
    snapshot = generation.get("generation_snapshot")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("resolved_data"), dict):
        raise AiGenerationError("该生成记录没有数据快照，请选择其他报告生成记录")
    original = snapshot.get("original_values")
    if not isinstance(original, dict):
        raise AiGenerationError("该生成记录没有字段取值快照，请选择其他报告生成记录")
    try:
        active = standard_context_payload(snapshot["resolved_data"])
    except ValueError as error:
        raise AiGenerationError("该生成记录的数据源快照格式无效") from error
    active, _ = prepare_ai_context(config, active, None, target_field)
    values = {}
    for variable in context_variables(config):
        group = variable.get("groupCode")
        code = str(group or variable["fieldCode"])
        values[code] = active.get(code) if group else original.get(code)
    records = []
    current_record = None
    per_record = needs_per_record_generation(config)
    if per_record:
        if not collection_code:
            raise AiGenerationError("当前记录模式需要指定 AI 字段所属编组")
        records = active.get(collection_code)
        if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
            raise AiGenerationError(f"编组 {collection_code} 的快照数据不是记录数组")
        if record_index is not None:
            if record_index < 0 or record_index >= len(records):
                raise AiGenerationError("所选编组记录不存在，请重新选择")
            current_record = records[record_index]
    values, current_record = prepare_ai_context(config, values, current_record, target_field)
    context, missing = resolve_context_values(config, values, current_record, context_fields)
    if per_record and records and record_index is None:
        # 数据存在但用户尚未选择记录，独立呈现待选择状态，不能误报提取缺失。
        current_codes = {str(v.get("groupCode") or v.get("fieldCode"))
                         for v in context_variables(config) if v.get("mode") == "CURRENT_RECORD"}
        missing = [code for code in missing if code not in current_codes]
    logger.info("导入报告AI测试上下文 generation=%s variables=%d missing=%s",
                generation.get("id"), len(context), ",".join(missing))
    return {"values": values, "context": context, "missing": missing,
            "records": records, "currentRecord": current_record, "requiresCurrentRecord": per_record}
