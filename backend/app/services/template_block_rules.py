"""把模板设计器里的"内容块"配置贴到字段映射上。

模板设计器的内容块现在是系统标准编组（admin_template_version_blocks），
一条记录对应一个编组：填充方式（kind）、Word 表格编号、循环数据集合、
去重/排序/空值/合并规则都在这里。生成器只认字段映射，所以发布快照里的
编组配置必须在这里落到每个字段映射上，否则设计器改了填充方式也不会生效。

本模块不猜测：字段所属编组没有配置内容块时，映射保持原样（不循环、不矩阵），
由生成器给出可见警告，而不是按 sourcePath 长得像数组就自作主张按行重复。
"""

from typing import Any


REPEATING_KINDS = {"REPEATING_TABLE", "MATRIX", "TABLE_REPEAT"}


def collection_source_path(path: str) -> str:
    """编组的数据集合路径统一成 `$.xxx[*]`，与字段映射的循环路径写法一致。"""
    text = str(path or "").strip()
    if not text or "[*]" in text:
        return text
    return f"{text}[*]"


def _group_of_field(field_groups: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(field.get("fieldCode") or ""): str(group.get("groupCode") or "")
        for group in field_groups
        for field in group.get("fields", [])
        if field.get("fieldCode")
    }


def _apply_block(mapping: dict[str, Any], block: dict[str, Any]) -> None:
    kind = str(block.get("kind") or "MAPPED_FIELD")
    mapping["contentBlockKind"] = kind
    mapping["blockSourcePath"] = collection_source_path(block.get("sourcePath", ""))
    mapping["blockDedupKey"] = block.get("dedupKey", "")
    mapping["blockSortRule"] = block.get("sortRule", "")
    mapping["blockEmptyBehavior"] = block.get("emptyBehavior", "KEEP")
    mapping["blockMergeRule"] = block.get("mergeRule", "NONE")
    mapping["prototypeLocation"] = block.get("prototypeLocation", "")
    if kind in REPEATING_KINDS:
        mapping["repeatType"] = "ROW"
        mapping["repeatKey"] = block.get("repeatKey", "")
        mapping["tableNo"] = block.get("tableNo", "") or mapping.get("tableNo", "")


def apply_template_block_rules(snapshot: dict[str, Any], field_groups: list[dict[str, Any]],
                               lims_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按标准编组把内容块配置与字段目录信息合并进映射列表。"""
    blocks = {
        str(item.get("standardGroupCode") or ""): item
        for item in snapshot.get("templateBlocks", [])
        if item.get("enabled", True)
    }
    group_of_field = _group_of_field(field_groups)
    catalog = {str(item.get("fieldCode") or ""): item for item in lims_fields}
    result: list[dict[str, Any]] = []
    for source in snapshot.get("mappings", []):
        mapping = dict(source)
        standard_code = str(mapping.get("standardFieldCode") or "")
        field = catalog.get(standard_code)
        # 取值路径只有标准字段目录一个权威来源：快照里可能带着绑定当时抄下的旧路径，一律覆盖。
        mapping["sourcePath"] = str(field.get("legacyJsonPath") or "") if field else ""
        if field:
            mapping["standardFieldDataType"] = field.get("dataType", "string")
            mapping["standardFieldOutputFormat"] = field.get("outputFormat", "")
        block = blocks.get(group_of_field.get(standard_code, ""))
        if block:
            mapping["standardGroupCode"] = block.get("standardGroupCode", "")
            _apply_block(mapping, block)
        result.append(mapping)
    return result
