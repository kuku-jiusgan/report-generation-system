import re
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..database_common import now_iso


REPORT_NUMBER_MIGRATION = "20260919_report_number_v1"
REPORT_NUMBER_PATTERN = re.compile(r"^JYD-(\d{8})-(\d+)$")


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


def _backfill_report_numbers(connection: Any, timezone_name: str) -> dict[str, int]:
    rows = connection.execute(
        "SELECT id,created_at,report_number FROM reports ORDER BY created_at,id"
    ).fetchall()
    used: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        report_number = str(row.get("report_number") or "").strip()
        if not report_number:
            continue
        match = REPORT_NUMBER_PATTERN.fullmatch(report_number)
        if not match:
            raise ValueError(f"报告 {row['id']} 的唯一编号格式无效：{report_number}")
        date_key, sequence_text = match.groups()
        sequence = int(sequence_text)
        if sequence < 1 or sequence in used[date_key]:
            raise ValueError(f"报告唯一编号冲突：{report_number}")
        used[date_key].add(sequence)

    updates: list[tuple[str, str]] = []
    for row in rows:
        if str(row.get("report_number") or "").strip():
            continue
        date_key = report_number_date(str(row["created_at"]), timezone_name)
        sequence = max(used[date_key], default=0) + 1
        used[date_key].add(sequence)
        updates.append((format_report_number(date_key, sequence), row["id"]))
    if updates:
        connection.executemany(
            "UPDATE reports SET report_number=%s WHERE id=%s", updates,
        )
    return {date_key: max(sequences) for date_key, sequences in used.items() if sequences}


def ensure_report_number_schema(database: Any) -> None:
    lock_name = "report-generation:report-number-v1"
    timezone_name = database.settings.report_number_timezone
    with database.connect() as connection:
        acquired = connection.execute(
            "SELECT GET_LOCK(%s,30) AS acquired", (lock_name,),
        ).fetchone()
        if not acquired or int(acquired["acquired"] or 0) != 1:
            raise RuntimeError("获取报告编号迁移锁超时")
        try:
            columns = {
                row["Field"] for row in connection.execute("SHOW COLUMNS FROM reports").fetchall()
            }
            if "report_number" not in columns:
                connection.execute(
                    "ALTER TABLE reports ADD COLUMN report_number VARCHAR(32) NULL AFTER id"
                )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS report_number_sequences (
                   report_date CHAR(8) PRIMARY KEY,
                   last_sequence INTEGER NOT NULL,
                   updated_at VARCHAR(64) NOT NULL
                   ) ENGINE=InnoDB"""
            )
            maximums = _backfill_report_numbers(connection, timezone_name)
            for date_key, sequence in maximums.items():
                connection.execute(
                    """INSERT INTO report_number_sequences(report_date,last_sequence,updated_at)
                       VALUES(%s,%s,%s) AS incoming
                       ON DUPLICATE KEY UPDATE
                       last_sequence=GREATEST(
                           report_number_sequences.last_sequence,
                           incoming.last_sequence
                       ),
                       updated_at=incoming.updated_at""",
                    (date_key, sequence, now_iso()),
                )
            indexes = connection.execute("SHOW INDEX FROM reports").fetchall()
            unique_columns = {
                row["Column_name"] for row in indexes if int(row["Non_unique"]) == 0
            }
            if "report_number" not in unique_columns:
                connection.execute(
                    "ALTER TABLE reports ADD UNIQUE KEY uq_reports_report_number(report_number)"
                )
            connection.execute(
                "ALTER TABLE reports MODIFY COLUMN report_number VARCHAR(32) NOT NULL"
            )
            connection.execute(
                "INSERT IGNORE INTO app_migrations(`key`,applied_at) VALUES(%s,%s)",
                (REPORT_NUMBER_MIGRATION, now_iso()),
            )
            connection.commit()
        finally:
            connection.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


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
