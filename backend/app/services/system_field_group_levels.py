"""编组的层级结构：数组形状由这里的配置生成，不靠路径字符串的约定。

一个编组默认只有"记录顶层"一层，字段直接挂在记录上，提取出来就是扁平数组。
用户可以在系统标准字段里给编组加下一层，每层有自己的键名和类型：

- OBJECT：记录下的一个子对象，每条记录一份；
- ARRAY：记录下的一个子数组，一条记录可以有多条。

字段挂在哪一层由 level_key 决定，字段路径和字段目录里的 JSON 路径都由层级推导，
用户不用也不该手写路径。没有配任何层的编组推导结果与过去完全一致。
"""

from typing import Any

from ..database import Database, now_iso


ROOT_LEVEL = ""
OBJECT = "OBJECT"
ARRAY = "ARRAY"
LEVEL_KINDS = (OBJECT, ARRAY)
CANONICAL_LEVEL_KINDS = {"summary": OBJECT, "injections": ARRAY}
CANONICAL_LEVEL_LABELS = {"summary": "汇总", "injections": "进样明细"}
LEGACY_LEVEL_ALIASES = {"mingxi": "injections"}


def ensure_group_levels(database: Database) -> None:
    with database.connect() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS system_field_group_levels (
          group_code VARCHAR(255) NOT NULL, level_key VARCHAR(255) NOT NULL,
          label VARCHAR(255) NOT NULL DEFAULT '', kind VARCHAR(32) NOT NULL DEFAULT 'OBJECT',
          parent_level_key VARCHAR(255) NOT NULL DEFAULT '',
          order_no INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
          PRIMARY KEY(group_code,level_key)
        ) ENGINE=InnoDB""")
        if isinstance(database, Database):
            columns = {row["Field"] for row in connection.execute(
                "SHOW COLUMNS FROM system_field_group_levels"
            ).fetchall()}
            if "parent_level_key" not in columns:
                connection.execute(
                    "ALTER TABLE system_field_group_levels ADD COLUMN parent_level_key VARCHAR(255) NOT NULL DEFAULT ''"
                )
        # 不声明外键：库的默认排序规则与 system_field_groups 建表时的不一致，
        # 外键会因排序规则不兼容建不起来；编组删除时在 delete_system_field_group 里显式清理。
        if isinstance(database, Database):
            columns = {row["Field"] for row in connection.execute(
                "SHOW COLUMNS FROM system_field_group_fields"
            ).fetchall()}
            if "level_key" not in columns:
                raise RuntimeError("system_field_group_fields 缺少 level_key 列，请检查数据库结构")


def list_group_levels(database: Database, group_code: str = "") -> dict[str, list[dict[str, Any]]]:
    ensure_group_levels(database)
    query = "SELECT * FROM system_field_group_levels"
    parameters: tuple[Any, ...] = ()
    if group_code:
        query += " WHERE group_code=%s"
        parameters = (group_code,)
    with database.connect() as connection:
        rows = [dict(row) for row in connection.execute(query + " ORDER BY order_no,level_key", parameters)]
    levels: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        levels.setdefault(row["group_code"], []).append({
            "levelKey": row["level_key"], "label": row["label"],
            "kind": row["kind"], "parentLevelKey": row.get("parent_level_key") or "",
            "orderNo": row["order_no"],
        })
    return levels


def field_path_for(level_key: str, kind: str, json_key: str,
                   levels: list[dict[str, Any]] | None = None) -> str:
    """字段在编组记录里的相对路径，由所属层的键名和类型推导。"""
    if not level_key:
        return json_key
    by_key = {str(item.get("levelKey")): item for item in levels or []}
    parts: list[str] = []
    current = level_key
    seen: set[str] = set()
    while current:
        if current in seen:
            raise ValueError(f"编组层级存在循环：{current}")
        seen.add(current)
        item = by_key.get(current)
        if levels is not None and item is None:
            raise ValueError(f"编组层级 {current} 不存在")
        current_kind = str(item.get("kind") if item else (kind if current == level_key else OBJECT))
        parts.append(f"{current}[*]" if current_kind == ARRAY else current)
        current = str(item.get("parentLevelKey") or "") if item else ""
    return ".".join([*reversed(parts), json_key])


def json_path_for(item_path: str, cardinality: str, field_path: str) -> str:
    """字段在报告载荷里的完整 JSON 路径。"""
    collection = str(item_path or "").strip() or "$"
    prefix = f"{collection}[*]" if cardinality == "MANY" else collection
    return f"{prefix}.{field_path}"


def save_group_level(database: Database, group_code: str, item: dict[str, Any],
                     original_key: str = "") -> None:
    ensure_group_levels(database)
    submitted_key = str(item.get("levelKey") or "").strip()
    if submitted_key in LEGACY_LEVEL_ALIASES:
        raise ValueError(f"层的键名 {submitted_key} 已废弃，请使用 {LEGACY_LEVEL_ALIASES[submitted_key]}")
    level_key = submitted_key
    if not level_key:
        raise ValueError("层的键名不能为空")
    if not level_key.replace("_", "").isalnum():
        raise ValueError("层的键名只能使用字母、数字和下划线")
    kind = str(item.get("kind") or OBJECT)
    if kind not in LEVEL_KINDS:
        raise ValueError("层类型只能是 OBJECT 或 ARRAY")
    parent_key = str(item.get("parentLevelKey") or "").strip()
    if parent_key == level_key:
        raise ValueError("层不能以自身作为父层")
    if parent_key and not parent_key.replace("_", "").isalnum():
        raise ValueError("父层键名无效")
    with database.connect() as connection:
        ancestor = parent_key
        seen: set[str] = set()
        while ancestor:
            if ancestor == level_key or ancestor in seen:
                raise ValueError("编组层级不能形成循环")
            seen.add(ancestor)
            parent = connection.execute(
                "SELECT parent_level_key FROM system_field_group_levels WHERE group_code=%s AND level_key=%s",
                (group_code, ancestor),
            ).fetchone()
            if parent is None:
                raise ValueError(f"父层 {ancestor} 不存在")
            ancestor = str(parent["parent_level_key"] or "")
        if original_key and original_key != level_key:
            raise ValueError("已有层的键名不能修改，请先迁移其字段和子层")
        existing_parent = connection.execute(
            "SELECT level_key FROM system_field_group_levels WHERE group_code=%s AND level_key=%s",
            (group_code, parent_key),
        ).fetchone() if parent_key else True
        if parent_key and not existing_parent:
            raise ValueError(f"父层 {parent_key} 不存在")
        connection.execute(
            "INSERT INTO system_field_group_levels(group_code,level_key,label,kind,parent_level_key,order_no,updated_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE label=VALUES(label),kind=VALUES(kind),"
            "parent_level_key=VALUES(parent_level_key),order_no=VALUES(order_no),updated_at=VALUES(updated_at)",
            (group_code, level_key, str(item.get("label") or CANONICAL_LEVEL_LABELS.get(level_key, level_key)), kind,
             parent_key,
             int(item.get("orderNo", 0)), now_iso()),
        )


def delete_group_level(database: Database, group_code: str, level_key: str) -> None:
    """删除一层：层里的字段回到记录顶层，不会连字段一起删掉。"""
    ensure_group_levels(database)
    with database.connect() as connection:
        child = connection.execute(
            "SELECT level_key FROM system_field_group_levels WHERE group_code=%s AND parent_level_key=%s",
            (group_code, level_key),
        ).fetchone()
        if child:
            raise ValueError(f"层 {level_key} 仍有子层，不能删除")
        connection.execute(
            "UPDATE system_field_group_fields SET level_key='' WHERE group_code=%s AND level_key=%s",
            (group_code, level_key),
        )
        connection.execute(
            "DELETE FROM system_field_group_levels WHERE group_code=%s AND level_key=%s",
            (group_code, level_key),
        )


def move_field_to_level(database: Database, group_code: str, field_code: str, level_key: str) -> None:
    ensure_group_levels(database)
    with database.connect() as connection:
        if level_key:
            exists = connection.execute(
                "SELECT 1 FROM system_field_group_levels WHERE group_code=%s AND level_key=%s",
                (group_code, level_key),
            ).fetchone()
            if not exists:
                raise ValueError(f"编组里没有名为 {level_key} 的层")
        updated = connection.execute(
            "UPDATE system_field_group_fields SET level_key=%s WHERE group_code=%s AND field_code=%s",
            (level_key, group_code, field_code),
        )
        del updated


def structure_preview(levels: list[dict[str, Any]], fields: list[dict[str, Any]]) -> dict[str, Any]:
    """按当前层级配置生成的记录结构预览：键名与嵌套关系，取值用字段名占位。"""
    by_level: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        by_level.setdefault(str(field.get("levelKey") or ROOT_LEVEL), []).append(field)
    record: dict[str, Any] = {
        str(field.get("jsonKey") or field["fieldCode"]): field.get("label") or field["fieldCode"]
        for field in by_level.get(ROOT_LEVEL, [])
    }
    def build(parent: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for level in [item for item in levels if str(item.get("parentLevelKey") or "") == parent]:
            inner = {str(field.get("jsonKey") or field["fieldCode"]): field.get("label") or field["fieldCode"]
                     for field in by_level.get(level["levelKey"], [])}
            inner.update(build(level["levelKey"]))
            result[level["levelKey"]] = [inner] if level["kind"] == ARRAY else inner
        return result
    record.update(build(""))
    return record
