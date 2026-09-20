"""把模板设计器里的"内容块"配置贴到字段映射上。

模板设计器的内容块现在是系统标准编组（admin_template_version_blocks），
一条记录对应一个编组：填充方式（kind）、Word 表格编号、循环数据集合、
去重/排序/空值/合并规则都在这里。生成器只认字段映射，所以发布快照里的
编组配置必须在这里落到每个字段映射上，否则设计器改了填充方式也不会生效。

本模块不猜测：字段所属编组没有配置内容块时，映射保持原样（不循环、不矩阵），
由生成器给出可见警告，而不是按 sourcePath 长得像数组就自作主张按行重复。
"""

from typing import Any

from .system_field_group_levels import json_path_for


REPEATING_KINDS = {"REPEATING_TABLE", "MATRIX", "TABLE_REPEAT"}


def collection_source_path(path: str) -> str:
    """编组的数据集合路径统一成 `$.xxx[*]`，与字段映射的循环路径写法一致。"""
    text = str(path or "").strip()
    if not text or "[*]" in text:
        return text
    return f"{text}[*]"


def _field_memberships(field_groups: list[dict[str, Any]]) -> dict[str, list[tuple[dict, dict]]]:
    memberships: dict[str, list[tuple[dict, dict]]] = {}
    for group in field_groups:
        for field in group.get("fields", []):
            code = str(field.get("fieldCode") or "")
            if code:
                memberships.setdefault(code, []).append((group, field))
    return memberships


def _mapping_group(mapping: dict[str, Any], field: dict[str, Any] | None,
                   memberships: list[tuple[dict, dict]],
                   chapter_codes: dict[int, str]) -> tuple[dict, dict] | None:
    if not memberships:
        return None
    chapter_id = mapping.get("chapterId") or mapping.get("assigned_chapter_id")
    chapter_code = chapter_codes.get(int(chapter_id)) if chapter_id else None
    if chapter_id and chapter_code is None:
        raise ValueError(f"模板章节 {chapter_id} 缺少稳定章节编码")
    chapter_matches = [
        item for item in memberships
        if chapter_code and chapter_code in item[0].get("chapterCodes", [])
    ]
    if len(chapter_matches) == 1:
        return chapter_matches[0]
    if len(chapter_matches) > 1:
        raise ValueError(
            f"字段 {mapping.get('standardFieldCode')} 在章节 {chapter_id} 关联了多个标准编组"
        )
    if len(memberships) == 1:
        return memberships[0]
    collection_code = str((field or {}).get("collectionCode") or "")
    collection_matches = [item for item in memberships
                          if str(item[0].get("groupCode") or "") == collection_code]
    if len(collection_matches) == 1:
        return collection_matches[0]
    raise ValueError(
        f"字段 {mapping.get('standardFieldCode')} 属于多个标准编组，当前模板位置无法确定取值编组"
    )


def _group_field_path(group: dict[str, Any], field: dict[str, Any]) -> str:
    item_path = str(group.get("itemPath") or f"$.{group.get('groupCode') or ''}")
    return json_path_for(item_path, str(group.get("cardinality") or "ONE"),
                         str(field.get("fieldPath") or ""))


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
    memberships = _field_memberships(field_groups)
    chapter_codes = {
        int(item["id"]): str(item["code"])
        for item in snapshot.get("chapters", [])
    }
    catalog = {str(item.get("fieldCode") or ""): item for item in lims_fields}
    result: list[dict[str, Any]] = []
    for source in snapshot.get("mappings", []):
        mapping = dict(source)
        standard_code = str(mapping.get("standardFieldCode") or "")
        field = catalog.get(standard_code)
        group_entry = _mapping_group(
            mapping, field, memberships.get(standard_code, []), chapter_codes,
        )
        # 同一字段可以出现在多个编组中，路径必须来自当前章节选中的编组成员关系。
        # 字段目录路径只用于没有编组归属的普通字段。
        mapping["sourcePath"] = (_group_field_path(*group_entry) if group_entry
                                 else str(field.get("legacyJsonPath") or "") if field else "")
        if field:
            mapping["standardFieldDataType"] = field.get("dataType", "string")
            mapping["standardFieldOutputFormat"] = field.get("outputFormat", "")
            mapping["standardFieldFillRule"] = field.get("fillRule", "")
        group_config = group_entry[0] if group_entry else None
        group_code = str(group_config.get("groupCode") or "") if group_config else ""
        block = blocks.get(group_code)
        if group_config and group_code:
            mapping["groupItemPath"] = collection_source_path(group_config.get("itemPath", ""))
        if block:
            mapping["standardGroupCode"] = block.get("standardGroupCode", "")
            _apply_block(mapping, block)
        result.append(mapping)
    return result
