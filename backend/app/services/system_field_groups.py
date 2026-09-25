import json
import re
from typing import Any

from ..database import Database, now_iso
from .excel_standard_path import excel_target_path
from .system_field_catalog_chapters import ensure_system_field_catalog_chapters
from .system_field_group_levels import (
    ensure_group_levels, field_path_for, json_path_for, list_group_levels,
)


_PATH_PATTERN = re.compile(r"^\$\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_SOURCE_TYPES = {"EXCEL", "PROTOCOL"}
def _default_item_path(group_code: str) -> str:
    """编组编码是数据集合的唯一名称，标准路径由系统统一推导。"""
    code = str(group_code or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", code):
        raise ValueError("编组编码必须以字母或下划线开头，且只能包含字母、数字和下划线")
    return f"$.{code}"


def _decode_source_mappings(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("编组来源映射不是合法 JSON") from error
    if not isinstance(decoded, list):
        raise ValueError("编组来源映射必须是数组")
    return decoded


def _validate_group_contract(item: dict[str, Any], fields: list[dict[str, Any]] | None = None) -> tuple[str, str, list[dict[str, Any]]]:
    cardinality = str(item.get("cardinality") or "ONE").upper()
    if cardinality not in {"ONE", "MANY"}:
        raise ValueError("编组基数只能是 ONE 或 MANY")
    group_code = str(item.get("groupCode") or "").strip()
    canonical_path = _default_item_path(group_code)
    submitted_path = str(item.get("itemPath") or "").strip()
    if submitted_path and not _PATH_PATTERN.fullmatch(submitted_path):
        raise ValueError("标准数据路径必须是形如 $.jiancexian 的 JSONPath，不能包含 [*]")
    if submitted_path and submitted_path != canonical_path:
        raise ValueError(f"标准数据路径必须由编组编码生成：{canonical_path}")
    mappings = _decode_source_mappings(item.get("sourceMappings", []))
    item_key = str(item.get("itemKey") or "").strip()
    if item_key:
        if cardinality != "MANY":
            raise ValueError("只有数组编组可以配置记录身份字段")
        matches = [field for field in (fields or [])
                   if str(field.get("levelKey") or field.get("level_key") or "") == ""
                   and str(field.get("jsonKey") or field.get("json_key") or "") == item_key]
        if len(matches) != 1:
            raise ValueError(f"编组记录身份字段 {item_key} 必须且只能对应一个根层字段")
    field_codes = {str(field.get("fieldCode")) for field in (fields or [])}
    seen_fields: set[tuple[str, str]] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("编组来源映射的每一项必须是对象")
        source_type = str(mapping.get("sourceType") or "").upper()
        if source_type not in _SOURCE_TYPES:
            raise ValueError("编组来源类型只能是 EXCEL 或 PROTOCOL；LIMS 请在字段提取规则中配置")
        if source_type == "PROTOCOL":
            from .protocol_rules import validate_protocol_locator
            from .protocol_row_expansion import validate_row_expansion
            validate_protocol_locator(mapping)
            validate_row_expansion(mapping, item, fields or [])
            if not mapping.get("headerPattern"):
                raise ValueError("方案来源映射必须配置表头正则")
            if cardinality != "MANY":
                raise ValueError("方案明细来源映射只能用于多行编组")
            if sum(entry.get("sourceType") == "PROTOCOL" for entry in mappings) != 1:
                raise ValueError("同一编组只能配置一条方案来源映射")
        mapping["sourceType"] = source_type
        columns = mapping.get("columnMappings", mapping.get("fieldMappings", mapping.get("columns", [])))
        if not isinstance(columns, list):
            raise ValueError("编组来源映射的列映射必须是数组")
        for column in columns:
            if not isinstance(column, dict):
                raise ValueError("编组列映射必须是对象")
            field_code = str(column.get("fieldCode") or "").strip()
            column_pattern = str(column.get("columnPattern", column.get("column", "")) or "").strip()
            if field_code not in field_codes:
                raise ValueError(f"来源映射字段不属于当前编组：{field_code}")
            if not column_pattern:
                raise ValueError(f"字段 {field_code} 的来源列匹配条件不能为空")
            if source_type == "PROTOCOL":
                try:
                    re.compile(column_pattern)
                except re.error as error:
                    raise ValueError(f"方案列正则无效：{error}") from error
            if (source_type, field_code) in seen_fields:
                raise ValueError(f"来源映射字段重复：{field_code}")
            seen_fields.add((source_type, field_code))
    return canonical_path, "", mappings


def ensure_system_field_groups(database: Database) -> None:
    with database.connect() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS system_field_groups (
          group_code VARCHAR(255) PRIMARY KEY, label VARCHAR(255) NOT NULL, description VARCHAR(2000) NOT NULL DEFAULT '',
          cardinality VARCHAR(64) NOT NULL DEFAULT 'ONE', item_path VARCHAR(1000) NOT NULL DEFAULT '',
          item_key VARCHAR(255) NOT NULL DEFAULT '', payload_key VARCHAR(255) NOT NULL DEFAULT '',
          source_mappings TEXT NOT NULL, order_no INTEGER NOT NULL DEFAULT 0,
          enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
        ) ENGINE=InnoDB""")
        if isinstance(database, Database):
            columns = {
                row["Field"]
                for row in connection.execute("SHOW COLUMNS FROM system_field_groups").fetchall()
            }
            missing = {"item_key", "payload_key", "source_mappings"} - columns
            if missing:
                raise RuntimeError(f"system_field_groups 缺少必要列：{', '.join(sorted(missing))}")
        connection.execute("""CREATE TABLE IF NOT EXISTS system_field_group_fields (
          group_code VARCHAR(255) NOT NULL, field_code VARCHAR(255) NOT NULL, field_path VARCHAR(1000) NOT NULL DEFAULT '',
          order_no INTEGER NOT NULL DEFAULT 0, required INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(group_code,field_code),
          FOREIGN KEY(group_code) REFERENCES system_field_groups(group_code) ON DELETE CASCADE,
          FOREIGN KEY(field_code) REFERENCES lims_field_catalog(field_code) ON UPDATE CASCADE ON DELETE CASCADE
        ) ENGINE=InnoDB""")
    ensure_group_levels(database)
    # Source-upload tests and lightweight adapters do not expose the catalog schema.
    if isinstance(database, Database):
        ensure_system_field_catalog_chapters(database)


def list_system_field_groups(database: Database) -> list[dict[str, Any]]:
    ensure_system_field_groups(database)
    ensure_group_levels(database)
    with database.connect() as connection:
        groups = [dict(row) for row in connection.execute("SELECT * FROM system_field_groups ORDER BY order_no,group_code")]
        fields = [dict(row) for row in connection.execute(
            """SELECT gf.*,f.label,f.data_type,f.cardinality AS field_cardinality,f.enabled,f.json_key
               FROM system_field_group_fields gf JOIN lims_field_catalog f ON f.field_code=gf.field_code
               ORDER BY gf.group_code,gf.order_no,gf.field_code"""
        )]
        links = connection.execute(
            """SELECT membership.group_code,membership.chapter_id,chapter.code
               FROM system_field_catalog_groups membership
               JOIN system_field_catalog_chapters chapter ON chapter.id=membership.chapter_id"""
        ).fetchall()
    levels = list_group_levels(database)
    # 字段路径由层级配置推导，不读库里那份旧的 field_path，避免两处打架
    level_items = {code: items for code, items in levels.items()}
    by_group: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        code, level_key = field["group_code"], str(field.get("level_key") or "")
        json_key = str(field.get("json_key") or "").strip() or str(field["field_code"]).rsplit(".", 1)[-1]
        by_group.setdefault(code, []).append({
            "fieldCode": field["field_code"], "label": field["label"], "dataType": field["data_type"],
            "cardinality": field["field_cardinality"], "enabled": bool(field["enabled"]),
            "jsonKey": json_key, "levelKey": level_key,
            "orderNo": int(field.get("order_no", 0) or 0),
            "fieldPath": field_path_for(
                level_key,
                next((item["kind"] for item in level_items.get(code, [])
                      if item["levelKey"] == level_key), ""),
                json_key,
                level_items.get(code, []),
            ),
        })
    chapters: dict[str, list[int]] = {}
    chapter_codes: dict[str, list[str]] = {}
    for link in links:
        chapters.setdefault(link["group_code"], []).append(link["chapter_id"])
        chapter_codes.setdefault(link["group_code"], []).append(str(link["code"]))
    return [{
        "groupCode": row["group_code"], "label": row["label"], "description": row["description"],
        "cardinality": row["cardinality"],
        "itemPath": _default_item_path(row["group_code"]),
        "itemKey": row["item_key"],
        "sourceMappings": _decode_source_mappings(row.get("source_mappings")),
        "orderNo": row["order_no"], "enabled": bool(row["enabled"]), "fieldCount": len(by_group.get(row["group_code"], [])),
        "fields": by_group.get(row["group_code"], []), "chapterIds": chapters.get(row["group_code"], []),
        "chapterCodes": chapter_codes.get(row["group_code"], []),
        "levels": levels.get(row["group_code"], []),
    } for row in groups]


def sync_group_field_paths(database: Database, group_code: str) -> None:
    """层级或字段归属变动后，把推导出的路径写回编组和字段目录，提取规则跟着走。"""
    group = next((item for item in list_system_field_groups(database)
                  if item["groupCode"] == group_code), None)
    if not group:
        return
    field_paths: dict[str, str] = {}
    with database.connect() as connection:
        for field in group["fields"]:
            canonical_path = json_path_for(_default_item_path(group_code), group["cardinality"], field["fieldPath"])
            field_paths[field["fieldCode"]] = canonical_path
            connection.execute(
                "UPDATE system_field_group_fields SET field_path=%s WHERE group_code=%s AND field_code=%s",
                (field["fieldPath"], group_code, field["fieldCode"]),
            )
            connection.execute(
                "UPDATE lims_field_catalog SET collection_code=%s,legacy_json_path=%s,updated_at=%s WHERE field_code=%s",
                (group_code, canonical_path, now_iso(), field["fieldCode"]),
            )
    for field_code, canonical_path in field_paths.items():
        field = {"fieldCode": field_code, "groupCode": group_code, "legacyJsonPath": canonical_path}
        for rule in database.list_system_field_rules(field_code):
            if rule.get("sourceType") != "EXCEL":
                continue
            config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
            target = excel_target_path(field, config.get("sourcePath"))
            if config.get("sourcePath") == target:
                continue
            database.save_system_field_rule({**rule, "config": {**config, "sourcePath": target}}, rule["id"])


def save_system_field_group(database: Database, item: dict[str, Any], original_code: str = "") -> dict[str, Any]:
    ensure_system_field_groups(database)
    code = str(item.get("groupCode") or original_code).strip()
    if not code:
        raise ValueError("编组编码不能为空")
    label = str(item.get("label") or "").strip()
    if not label:
        raise ValueError("编组名称不能为空")
    existing_fields: list[dict[str, Any]] = []
    existing_item: dict[str, Any] = {}
    with database.connect() as connection:
        row = connection.execute("SELECT * FROM system_field_groups WHERE group_code=%s", (original_code or code,)).fetchone()
        existing_item = dict(row) if row else {}
        existing_fields = [dict(row) for row in connection.execute(
            """SELECT gf.field_code,gf.level_key,f.json_key
               FROM system_field_group_fields gf
               JOIN lims_field_catalog f ON f.field_code=gf.field_code
               WHERE gf.group_code=%s""", (original_code or code,)
        ).fetchall()]
    existing_item = {
        "cardinality": existing_item.get("cardinality", "ONE"),
        "itemPath": existing_item.get("item_path", ""),
        "itemKey": existing_item.get("item_key", ""),
        "sourceMappings": _decode_source_mappings(existing_item.get("source_mappings")),
    }
    merged = {**existing_item, **item}
    merged["cardinality"] = str(item.get("cardinality") or existing_item["cardinality"] or "ONE")
    submitted_fields = item.get("fields") if isinstance(item.get("fields"), list) else None
    valid_fields = submitted_fields if submitted_fields is not None else [
        {"fieldCode": row.get("field_code")} for row in existing_fields
    ]
    item_path, payload_key, source_mappings = _validate_group_contract(merged, valid_fields)
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO system_field_groups(group_code,label,description,cardinality,item_path,item_key,payload_key,source_mappings,order_no,enabled,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE label=VALUES(label),
               description=VALUES(description),cardinality=VALUES(cardinality),item_path=VALUES(item_path),
               item_key=VALUES(item_key),payload_key=VALUES(payload_key),source_mappings=VALUES(source_mappings),
               order_no=VALUES(order_no),enabled=VALUES(enabled),updated_at=VALUES(updated_at)""",
            (code, label, item.get("description", ""), merged["cardinality"], item_path,
             merged.get("itemKey", ""), payload_key, json.dumps(source_mappings, ensure_ascii=False),
             int(item.get("orderNo", 0)), int(item.get("enabled", True)), now_iso()),
        )
    return next(group for group in list_system_field_groups(database) if group["groupCode"] == code)


def delete_system_field_group(database: Database, group_code: str) -> bool:
    ensure_system_field_groups(database)
    with database.connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM system_field_groups WHERE group_code=%s", (group_code,)
        ).fetchone()
        if not exists:
            return False
        fields = [str(row["field_code"]) for row in connection.execute(
            "SELECT field_code FROM system_field_group_fields WHERE group_code=%s", (group_code,),
        ).fetchall()]
        if fields:
            raise ValueError(
                f"编组 {group_code} 仍包含 {len(fields)} 个字段，请先移动字段后再删除"
            )
        connection.execute("DELETE FROM system_field_group_levels WHERE group_code=%s", (group_code,))
        connection.execute("DELETE FROM system_field_catalog_groups WHERE group_code=%s", (group_code,))
        connection.execute("DELETE FROM system_field_groups WHERE group_code=%s", (group_code,))
    return True


def assign_field_to_group(database: Database, group_code: str, field_code: str, field_path: str = "") -> dict[str, Any]:
    ensure_system_field_groups(database)
    if not database.get_lims_field(field_code):
        raise ValueError("系统字段不存在")
    with database.connect() as connection:
        connection.execute("DELETE FROM system_field_catalog_fields WHERE field_code=%s", (field_code,))
        connection.execute(
            "INSERT INTO system_field_group_fields(group_code,field_code,field_path,order_no) VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE field_path=VALUES(field_path),order_no=VALUES(order_no)",
            (group_code, field_code, field_path, 0),
        )
    sync_group_field_paths(database, group_code)
    return next(group for group in list_system_field_groups(database) if group["groupCode"] == group_code)


def move_field_ownership(
    database: Database, field_code: str, *, group_code: str = "", chapter_id: int | None = None,
) -> dict[str, Any]:
    """将字段移动到唯一的目录归属，不改动字段本身的取值路径或提取规则。"""
    ensure_system_field_groups(database)
    target_group = group_code.strip()
    if bool(target_group) == (chapter_id is not None):
        raise ValueError("请选择一个目标章节或目标编组")
    if not database.get_lims_field(field_code):
        raise ValueError("系统字段不存在")
    with database.connect() as connection:
        if target_group:
            if not connection.execute(
                "SELECT 1 FROM system_field_groups WHERE group_code=%s", (target_group,),
            ).fetchone():
                raise ValueError("目标编组不存在")
        elif not connection.execute(
            "SELECT 1 FROM system_field_catalog_chapters WHERE id=%s", (chapter_id,),
        ).fetchone():
            raise ValueError("目标章节不存在")

        # 目录归属是单值关系：移动时必须先清除所有旧位置，不能让同一字段出现在多处。
        connection.execute("DELETE FROM system_field_group_fields WHERE field_code=%s", (field_code,))
        connection.execute("DELETE FROM system_field_catalog_fields WHERE field_code=%s", (field_code,))
        if target_group:
            next_order = connection.execute(
                "SELECT COALESCE(MAX(order_no), -1) + 1 AS next_order FROM system_field_group_fields WHERE group_code=%s",
                (target_group,),
            ).fetchone()["next_order"]
            connection.execute(
                "INSERT INTO system_field_group_fields(group_code,field_code,field_path,order_no) VALUES(%s,%s,%s,%s)",
                (target_group, field_code, "", next_order),
            )
        else:
            order_no = connection.execute(
                "SELECT order_no FROM lims_field_catalog WHERE field_code=%s", (field_code,),
            ).fetchone()["order_no"]
            connection.execute(
                "INSERT INTO system_field_catalog_fields(field_code,chapter_id,order_no) VALUES(%s,%s,%s)",
                (field_code, chapter_id, order_no),
            )
    if target_group:
        sync_group_field_paths(database, target_group)
    moved = database.get_lims_field(field_code)
    if not moved:
        raise ValueError("字段移动后无法读取")
    return moved

def remove_field_from_group(database: Database, group_code: str, field_code: str) -> dict[str, Any]:
    ensure_system_field_groups(database)
    with database.connect() as connection:
        connection.execute("DELETE FROM system_field_group_fields WHERE group_code=%s AND field_code=%s", (group_code, field_code))
    return next(group for group in list_system_field_groups(database) if group["groupCode"] == group_code)

def reorder_group_fields(database: Database, group_code: str, field_codes: list[str]) -> dict[str, Any]:
    ensure_system_field_groups(database)
    with database.connect() as connection:
        current = [str(row["field_code"]) for row in connection.execute(
            "SELECT field_code FROM system_field_group_fields WHERE group_code=%s ORDER BY order_no,field_code", (group_code,)
        ).fetchall()]
        if len(field_codes) != len(current) or set(field_codes) != set(current):
            raise ValueError("字段排序列表与当前编组字段不一致")
        for order_no, field_code in enumerate(field_codes):
            connection.execute("UPDATE system_field_group_fields SET order_no=%s WHERE group_code=%s AND field_code=%s", (order_no, group_code, field_code))
    return next(group for group in list_system_field_groups(database) if group["groupCode"] == group_code)


def assign_group_to_chapter(database: Database, group_code: str, chapter_id: int) -> dict[str, Any]:
    ensure_system_field_groups(database)
    with database.connect() as connection:
        if not connection.execute("SELECT 1 FROM system_field_groups WHERE group_code=%s", (group_code,)).fetchone():
            raise ValueError("编组不存在")
        if not connection.execute(
            "SELECT 1 FROM system_field_catalog_chapters WHERE id=%s", (chapter_id,),
        ).fetchone():
            raise ValueError("章节不存在")
        # 一个编组在目录中只归属一个章节；重新选择时执行移动，而不是追加。
        connection.execute("DELETE FROM system_field_catalog_groups WHERE group_code=%s", (group_code,))
        connection.execute(
            "INSERT INTO system_field_catalog_groups(group_code,chapter_id) VALUES(%s,%s)",
            (group_code, chapter_id),
        )
    return next(group for group in list_system_field_groups(database) if group["groupCode"] == group_code)
