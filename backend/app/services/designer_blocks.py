from typing import Any


def _catalog_fields_by_chapter(chapters: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    pending = list(chapters)
    while pending:
        chapter = pending.pop()
        result[int(chapter["id"])] = list(chapter.get("fields", []))
        pending.extend(chapter.get("children", []))
    return result


def _chapter_ids_by_code(chapters: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    pending = list(chapters)
    while pending:
        chapter = pending.pop()
        result[str(chapter["code"])] = int(chapter["id"])
        pending.extend(chapter.get("children", []))
    return result


def _catalog_codes_by_id(chapters: list[dict[str, Any]]) -> dict[int, str]:
    result: dict[int, str] = {}
    pending = list(chapters)
    while pending:
        chapter = pending.pop()
        result[int(chapter["id"])] = str(chapter["code"])
        pending.extend(chapter.get("children", []))
    return result


def _mappings_for_fields(
    mappings: list[dict[str, Any]], chapter_id: int, fields: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    codes = {field["fieldCode"] for field in fields}
    return [
        item for item in mappings
        if item.get("standardFieldCode") in codes
        and (item.get("chapterId") == chapter_id or not item.get("chapterId"))
    ]


def _table_for_group(
    table_rules: list[dict[str, Any]], group_code: str, configured: dict[str, Any],
) -> dict[str, Any] | None:
    table_no = configured.get("tableNo") or f"GROUP:{group_code}"
    table = next((rule for rule in table_rules if rule.get("tableNo") == table_no), None)
    if table is None:
        table = next((rule for rule in table_rules if rule.get("groupKey") == group_code), None)
    if table is None and configured:
        table = next((
            rule for rule in table_rules
            if rule.get("sectionCode") == configured.get("sectionCode") and rule.get("tableNo")
        ), None)
    return table


def _field_block(chapter_id: int, fields: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> dict[str, Any]:
    items = _mappings_for_fields(mappings, chapter_id, fields)
    return {
        "id": -(chapter_id * 1000 + 999), "chapterId": chapter_id,
        "title": "章节字段", "kind": "MAPPED_FIELD", "tableNo": "",
        "standardFields": fields, "orderNo": -1, "sourcePath": "", "repeatKey": "",
        "prototypeLocation": "", "dedupKey": "", "sortRule": "",
        "emptyBehavior": "KEEP", "mergeRule": "NONE", "enabled": True,
        "mappingIds": [item["id"] for item in items],
        "controlTags": [item.get("controlTag") for item in items if item.get("controlTag")],
        "sources": sorted({item.get("sourceType") for item in items if item.get("sourceType")}),
        "status": "READY", "mappings": items, "tableRule": None,
    }


def _group_block(
    chapter_id: int, index: int, group: dict[str, Any], mappings: list[dict[str, Any]],
    configured: dict[str, Any], table_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    items = _mappings_for_fields(mappings, chapter_id, group.get("fields", []))
    table = _table_for_group(table_rules, group["groupCode"], configured)
    return {
        "id": -(chapter_id * 1000 + index + 1), "chapterId": chapter_id,
        "title": configured.get("title") or group["label"],
        "kind": configured.get("kind") or "MAPPED_FIELD",
        "tableNo": configured.get("tableNo", ""),
        "standardGroupCode": group["groupCode"], "standardFields": group.get("fields", []),
        "orderNo": configured.get("orderNo", index),
        "sourcePath": configured.get("sourcePath") or f"$.{group['groupCode']}",
        "repeatKey": configured.get("repeatKey") or group.get("itemKey", ""),
        "prototypeLocation": configured.get("prototypeLocation", ""),
        "dedupKey": configured.get("dedupKey", ""), "sortRule": configured.get("sortRule", ""),
        "emptyBehavior": configured.get("emptyBehavior", "KEEP"),
        "mergeRule": configured.get("mergeRule", "NONE"),
        "enabled": configured.get("enabled", group.get("enabled", True)),
        "mappingIds": [item["id"] for item in items],
        "controlTags": [item.get("controlTag") for item in items if item.get("controlTag")],
        "sources": sorted({item.get("sourceType") for item in items if item.get("sourceType")}),
        "status": "READY" if configured else "UNCONFIGURED", "mappings": items, "tableRule": table,
    }


def designer_blocks(
    catalog_chapters: list[dict[str, Any]], template_chapters: list[dict[str, Any]],
    standard_groups: list[dict[str, Any]],
    mappings: list[dict[str, Any]], configured_blocks: dict[str, dict[str, Any]],
    table_rules: list[dict[str, Any]],
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]]]:
    template_ids = _chapter_ids_by_code(template_chapters)
    catalog_codes = _catalog_codes_by_id(catalog_chapters)
    groups_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for group in standard_groups:
        for chapter_code in group.get("chapterCodes", []):
            template_id = template_ids.get(str(chapter_code))
            if template_id is not None:
                groups_by_chapter.setdefault(template_id, []).append(group)

    blocks_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for catalog_id, fields in _catalog_fields_by_chapter(catalog_chapters).items():
        template_id = template_ids.get(catalog_codes[catalog_id])
        if fields and template_id is not None:
            blocks_by_chapter.setdefault(template_id, []).append(
                _field_block(template_id, fields, mappings)
            )
    for chapter_id, groups in groups_by_chapter.items():
        for index, group in enumerate(groups):
            configured = configured_blocks.get(group["groupCode"], {})
            blocks_by_chapter.setdefault(chapter_id, []).append(
                _group_block(chapter_id, index, group, mappings, configured, table_rules)
            )
    return blocks_by_chapter, groups_by_chapter
