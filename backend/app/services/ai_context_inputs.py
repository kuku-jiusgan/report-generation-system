from copy import deepcopy
import logging
import re
from typing import Any

from .ai_field_generator import AiGenerationError, context_variables


logger = logging.getLogger(__name__)
_PATH = re.compile(r"^\$\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\*\])?)*$")


def _remove_path(value: Any, parts: list[str]) -> None:
    if not parts:
        return
    if not isinstance(value, dict):
        raise AiGenerationError("AI 上下文中的目标字段父级必须是对象")
    part, *remaining = parts
    many = part.endswith("[*]")
    key = part[:-3] if many else part
    if not remaining:
        value.pop(key, None)
    elif key in value:
        child = value[key]
        if child is None:
            return
        if many:
            if not isinstance(child, list):
                raise AiGenerationError(f"AI 上下文路径 {part} 要求数组数据")
            for record in child:
                _remove_path(record, remaining)
        else:
            _remove_path(child, remaining)


def prepare_ai_context(config: dict[str, Any], values: dict[str, Any],
                       current_record: dict[str, Any] | None,
                       target_field: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """从输入副本排除目标字段，所有 AI 生成入口共用，绝不改写来源数据。"""
    inputs = deepcopy(values)
    record = deepcopy(current_record)
    if target_field is None:
        return inputs, record
    code = str(target_field.get("fieldCode") or "")
    if any(variable.get("fieldCode") == code for variable in context_variables(config)):
        raise AiGenerationError(f"AI 规则不能引用正在生成的字段自身：{code}")
    path = str(target_field.get("legacyJsonPath") or "")
    if not code or not _PATH.fullmatch(path):
        raise AiGenerationError("AI 目标字段缺少有效的标准数据路径")
    inputs.pop(code, None)
    parts = path[2:].split(".")
    _remove_path(inputs, parts)
    if record is not None:
        # 编组集合路径不含通配符；首个 [*] 精确标记当前编组记录的边界。
        boundary = next((index for index, part in enumerate(parts) if part.endswith("[*]")), None)
        if boundary is None or boundary == len(parts) - 1:
            raise AiGenerationError("按记录生成的目标字段必须具有编组记录内的标准路径")
        _remove_path(record, parts[boundary + 1:])
    logger.info("AI上下文排除目标字段 field=%s path=%s", code, path)
    return inputs, record
