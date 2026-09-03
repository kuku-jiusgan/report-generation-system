"""按标准 JSON 路径把提取到的值写进报告载荷。

路径里的 `[*]` 表示一层数组。一层的老形状（`$.samples[*].batchNo`）按位置逐条落位；
两层的分层形状（`$.systemSuitability[*].injections[*].retentionTime`）要把一串扁平值
按分组切开：分组数取外层数组已有的长度，每组条数 = 值总数 ÷ 分组数。

所以写入必须先写分组层字段（它建立外层数组），再写明细层字段。切不开时立即报错，
不猜分组边界——猜错会把某个杂质的数据串到另一个杂质名下。
"""

from typing import Any


class PayloadPathError(ValueError):
    pass


def path_depth(path: str) -> int:
    """路径里的数组层数，用来决定写入顺序：层数少的先写。"""
    return str(path).count("[*]")


def _segments(path: str) -> list[tuple[str, bool]]:
    parts = [part for part in str(path).removeprefix("$").lstrip(".").split(".") if part]
    return [(part.replace("[*]", ""), "[*]" in part) for part in parts]


def _ensure_list(owner: dict[str, Any], key: str, length: int) -> list[dict[str, Any]]:
    collection = owner.get(key)
    if not isinstance(collection, list):
        collection = []
        owner[key] = collection
    while len(collection) < length:
        collection.append({})
    for index, item in enumerate(collection):
        if not isinstance(item, dict):
            collection[index] = {}
    return collection


def _split(values: list[Any], groups: int, path: str) -> list[list[Any]]:
    if groups < 1:
        raise PayloadPathError(f"{path}：外层数组还没有建立，无法确定分组数；请先配置分组层的字段")
    if len(values) % groups:
        raise PayloadPathError(
            f"{path}：提取到 {len(values)} 个值，无法平均分给 {groups} 个分组；"
            f"请检查该字段的 Excel 提取规则与编组层级配置是否一致"
        )
    size = len(values) // groups
    return [values[index * size:(index + 1) * size] for index in range(groups)]


def set_payload_path(payload: dict[str, Any], path: str, value: Any) -> None:
    segments = _segments(path)
    if not segments:
        raise PayloadPathError("标准 JSON 路径为空")
    arrays = [index for index, (_, many) in enumerate(segments) if many]
    if not arrays:
        current: Any = payload
        for key, _ in segments[:-1]:
            current = current.setdefault(key, {})
        current[segments[-1][0]] = value
        return
    values = value if isinstance(value, list) else [value]
    _write_array(payload, segments, arrays, values, path)


def _write_array(payload: dict[str, Any], segments: list[tuple[str, bool]], arrays: list[int],
                 values: list[Any], path: str) -> None:
    outer_key = segments[arrays[0]][0]
    owner: Any = payload
    for key, _ in segments[:arrays[0]]:
        owner = owner.setdefault(key, {})
    if len(arrays) == 1:
        collection = _ensure_list(owner, outer_key, len(values))
        _assign(collection, segments[arrays[0] + 1:], values, path)
        return
    # 两层及以上：外层必须已经存在，用它的长度切分这串扁平值
    existing = owner.get(outer_key)
    groups = len(existing) if isinstance(existing, list) else 0
    collection = _ensure_list(owner, outer_key, groups)
    for record, chunk in zip(collection, _split(values, groups, path)):
        _write_array(record, segments[arrays[0] + 1:], [index - arrays[0] - 1 for index in arrays[1:]],
                     chunk, path)


def _assign(collection: list[dict[str, Any]], tail: list[tuple[str, bool]], values: list[Any],
            path: str) -> None:
    if not tail:
        raise PayloadPathError(f"{path}：数组路径后面必须再跟一个字段名")
    for record, item in zip(collection, values):
        target = record
        for key, _ in tail[:-1]:
            nested = target.get(key)
            if not isinstance(nested, dict):
                nested = {}
                target[key] = nested
            target = nested
        if isinstance(item, dict):
            target.update(item)
        else:
            target[tail[-1][0]] = item
