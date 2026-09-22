import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..database_common import now_iso


def report_number_date(timestamp: str, timezone_name: str) -> str:
    try:
        moment = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError) as error:
        raise ValueError(f"报告创建时间格式无效：{timestamp}") from error
    if moment.tzinfo is None:
        raise ValueError(f"报告创建时间缺少时区：{timestamp}")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"报告编号时区无效：{timezone_name}") from error
    return moment.astimezone(timezone).strftime("%Y%m%d")


def format_report_number(date_key: str, sequence: int) -> str:
    if not re.fullmatch(r"\d{8}", date_key):
        raise ValueError(f"报告编号日期无效：{date_key}")
    if sequence < 1:
        raise ValueError("报告编号序号必须大于 0")
    return f"JYD-{date_key}-{sequence:03d}"


def ensure_report_number_schema(database: Any) -> None:
    with database.connect() as connection:
        columns = {row["Field"]: row for row in connection.execute("SHOW COLUMNS FROM reports").fetchall()}
        number = columns.get("report_number")
        if not number or number["Null"] != "NO":
            raise RuntimeError("报告编号列缺失或允许为空，请检查数据库结构")
        indexes = connection.execute("SHOW INDEX FROM reports").fetchall()
        if not any(row["Column_name"] == "report_number" and int(row["Non_unique"]) == 0
                   for row in indexes):
            raise RuntimeError("报告编号缺少唯一索引，请检查数据库结构")
        sequences = connection.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='report_number_sequences'"
        ).fetchone()
        if not sequences:
            raise RuntimeError("报告编号序列表不存在，请检查数据库结构")


def next_report_number(connection: Any, date_key: str) -> str:
    connection.execute(
        """INSERT INTO report_number_sequences(report_date,last_sequence,updated_at)
           VALUES(%s,1,%s) AS incoming
           ON DUPLICATE KEY UPDATE
           last_sequence=report_number_sequences.last_sequence+1,
           updated_at=incoming.updated_at""",
        (date_key, now_iso()),
    )
    row = connection.execute(
        "SELECT last_sequence FROM report_number_sequences WHERE report_date=%s FOR UPDATE",
        (date_key,),
    ).fetchone()
    if not row:
        raise RuntimeError("报告编号序号生成失败")
    return format_report_number(date_key, int(row["last_sequence"]))
