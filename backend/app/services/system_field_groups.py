from typing import Any

from ..database import Database, now_iso


GROUP_LABELS = {
    "samples": "样品信息", "referenceStandards": "对照品信息", "instruments": "仪器信息",
    "columns": "色谱柱信息", "reagents": "试剂信息", "systemSuitability": "系统适用性结果",
    "validationSummary": "验证结果汇总", "methodParameters": "分析方法参数",
    "narrative": "报告叙述", "project": "项目信息", "document": "文档信息",
    "approval": "审批信息", "impurity": "杂质信息", "limit": "限度结果",
    "accuracySolutions": "准确度溶液", "intermediatePrecisionSolutions": "中间精密度溶液",
    "lodSolutions": "检测限与定量限溶液", "repeatabilitySolutions": "重复性溶液",
    "robustnessSequence": "耐用性进样序列", "robustnessSolutions": "耐用性溶液",
    "robustnessSpecificity": "耐用性专属性", "specificity": "专属性结果",
    "specificitySolutions": "专属性溶液", "stabilitySolutions": "溶液稳定性溶液",
    "systemSuitabilitySolutions": "系统适用性溶液",
}


def ensure_system_field_groups(database: Database) -> None:
    with database.connect() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS system_field_groups (
          group_code VARCHAR(255) PRIMARY KEY, label VARCHAR(255) NOT NULL, description VARCHAR(2000) NOT NULL DEFAULT '',
          cardinality VARCHAR(64) NOT NULL DEFAULT 'ONE', item_path VARCHAR(1000) NOT NULL DEFAULT '',
          item_key VARCHAR(255) NOT NULL DEFAULT '', order_no INTEGER NOT NULL DEFAULT 0,
          enabled INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
        ) ENGINE=InnoDB""")
        connection.execute("""CREATE TABLE IF NOT EXISTS system_field_group_fields (
          group_code VARCHAR(255) NOT NULL, field_code VARCHAR(255) NOT NULL, field_path VARCHAR(1000) NOT NULL DEFAULT '',
          order_no INTEGER NOT NULL DEFAULT 0, required INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(group_code,field_code),
          FOREIGN KEY(group_code) REFERENCES system_field_groups(group_code) ON DELETE CASCADE,
          FOREIGN KEY(field_code) REFERENCES lims_field_catalog(field_code) ON UPDATE CASCADE ON DELETE CASCADE
        ) ENGINE=InnoDB""")
        connection.execute("""CREATE TABLE IF NOT EXISTS system_field_group_chapters (
          group_code VARCHAR(255) NOT NULL, chapter_id INTEGER NOT NULL, order_no INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(group_code,chapter_id),
          FOREIGN KEY(group_code) REFERENCES system_field_groups(group_code) ON DELETE CASCADE,
          FOREIGN KEY(chapter_id) REFERENCES admin_template_chapters(id) ON DELETE CASCADE
        ) ENGINE=InnoDB""")
        connection.execute("""CREATE TABLE IF NOT EXISTS system_field_chapters (
          field_code VARCHAR(255) NOT NULL, chapter_id INTEGER NOT NULL, order_no INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(field_code,chapter_id)
        ) ENGINE=InnoDB""")
        # 历史数据曾把同一编组写成 Approval/approval，统一到小写编码。
        if connection.execute("SELECT 1 FROM system_field_groups WHERE group_code='Approval'").fetchone():
            connection.execute(
                "INSERT IGNORE INTO system_field_group_fields(group_code,field_code,field_path,order_no,required) "
                "SELECT 'approval',field_code,field_path,order_no,required FROM system_field_group_fields WHERE group_code='Approval'"
            )
            connection.execute("DELETE FROM system_field_group_fields WHERE group_code='Approval'")
            connection.execute("DELETE FROM system_field_groups WHERE group_code='Approval'")


def list_system_field_groups(database: Database) -> list[dict[str, Any]]:
    ensure_system_field_groups(database)
    with database.connect() as connection:
        groups = [dict(row) for row in connection.execute("SELECT * FROM system_field_groups ORDER BY order_no,group_code")]
        fields = [dict(row) for row in connection.execute(
            """SELECT gf.*,f.label,f.data_type,f.cardinality AS field_cardinality,f.enabled
               FROM system_field_group_fields gf JOIN lims_field_catalog f ON f.field_code=gf.field_code
               ORDER BY gf.group_code,gf.order_no,gf.field_code"""
        )]
        links = connection.execute("SELECT group_code,chapter_id FROM system_field_group_chapters").fetchall()
    by_group: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        by_group.setdefault(field["group_code"], []).append({
            "fieldCode": field["field_code"], "label": field["label"], "dataType": field["data_type"],
            "cardinality": field["field_cardinality"], "fieldPath": field["field_path"], "enabled": bool(field["enabled"]),
        })
    chapters: dict[str, list[int]] = {}
    for link in links:
        chapters.setdefault(link["group_code"], []).append(link["chapter_id"])
    return [{
        "groupCode": row["group_code"], "label": row["label"], "description": row["description"],
        "cardinality": row["cardinality"], "itemPath": row["item_path"], "itemKey": row["item_key"],
        "orderNo": row["order_no"], "enabled": bool(row["enabled"]), "fieldCount": len(by_group.get(row["group_code"], [])),
        "fields": by_group.get(row["group_code"], []), "chapterIds": chapters.get(row["group_code"], []),
    } for row in groups]


def save_system_field_group(database: Database, item: dict[str, Any], original_code: str = "") -> dict[str, Any]:
    ensure_system_field_groups(database)
    code = str(item.get("groupCode") or original_code).strip()
    if not code:
        raise ValueError("编组编码不能为空")
    label = str(item.get("label") or "").strip()
    if not label:
        raise ValueError("编组名称不能为空")
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO system_field_groups(group_code,label,description,cardinality,item_path,item_key,order_no,enabled,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE label=VALUES(label),
               description=VALUES(description),cardinality=VALUES(cardinality),item_path=VALUES(item_path),
               item_key=VALUES(item_key),order_no=VALUES(order_no),enabled=VALUES(enabled),updated_at=VALUES(updated_at)""",
            (code, label, item.get("description", ""), item.get("cardinality", "ONE"), item.get("itemPath", ""),
             item.get("itemKey", ""), int(item.get("orderNo", 0)), int(item.get("enabled", True)), now_iso()),
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
        connection.execute("DELETE FROM system_field_group_fields WHERE group_code=%s", (group_code,))
        connection.execute("DELETE FROM system_field_group_chapters WHERE group_code=%s", (group_code,))
        connection.execute("DELETE FROM system_field_groups WHERE group_code=%s", (group_code,))
    return True


def assign_field_to_group(database: Database, group_code: str, field_code: str, field_path: str = "") -> dict[str, Any]:
    ensure_system_field_groups(database)
    if not database.get_lims_field(field_code):
        raise ValueError("系统字段不存在")
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO system_field_group_fields(group_code,field_code,field_path,order_no) VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE field_path=VALUES(field_path),order_no=VALUES(order_no)",
            (group_code, field_code, field_path, 0),
        )
    return next(group for group in list_system_field_groups(database) if group["groupCode"] == group_code)

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
        if not connection.execute("SELECT 1 FROM admin_template_chapters WHERE id=%s", (chapter_id,)).fetchone():
            raise ValueError("章节不存在")
        # 一个编组在目录中只归属一个章节；重新选择时执行移动，而不是追加。
        connection.execute("DELETE FROM system_field_group_chapters WHERE group_code=%s", (group_code,))
        connection.execute("INSERT INTO system_field_group_chapters(group_code,chapter_id) VALUES(%s,%s)", (group_code, chapter_id))
    return next(group for group in list_system_field_groups(database) if group["groupCode"] == group_code)
