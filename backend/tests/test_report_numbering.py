import threading

from backend.app.services.report_numbering import (
    REPORT_NUMBER_MIGRATION,
    ensure_report_number_schema,
    format_report_number,
    report_number_date,
)
from backend.tests.database_helpers import make_test_database


def report_item(identifier: str, created_at: str) -> dict:
    return {
        "id": identifier,
        "title": f"报告 {identifier}",
        "status": "DATA_REVIEW",
        "resolved_data": {},
        "created_at": created_at,
        "updated_at": created_at,
    }


def test_report_number_uses_shanghai_calendar_date() -> None:
    assert report_number_date("2026-09-18T16:30:00+00:00", "Asia/Shanghai") == "20260919"
    assert format_report_number("20260919", 1) == "JYD-20260919-001"
    assert format_report_number("20260919", 1000) == "JYD-20260919-1000"


def test_report_numbers_increment_daily_without_reuse(tmp_path) -> None:
    database = make_test_database(tmp_path)
    first = database.create_report(report_item("first", "2026-09-19T01:00:00+00:00"))
    second = database.create_report(report_item("second", "2026-09-19T02:00:00+00:00"))
    database.delete_report(first["id"])
    third = database.create_report(report_item("third", "2026-09-19T03:00:00+00:00"))
    next_day = database.create_report(report_item("next-day", "2026-09-19T16:00:00+00:00"))

    assert second["report_number"] == "JYD-20260919-002"
    assert third["report_number"] == "JYD-20260919-003"
    assert next_day["report_number"] == "JYD-20260920-001"


def test_existing_reports_receive_numbers_before_new_reports(tmp_path) -> None:
    database = make_test_database(tmp_path)
    database.ensure_report_number_schema()
    with database.connect() as connection:
        connection.execute(
            "ALTER TABLE reports MODIFY COLUMN report_number VARCHAR(32) NULL"
        )
        connection.executemany(
            """INSERT INTO reports(
                   id,title,status,resolved_data,created_at,updated_at,word_edit_locked
               ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            [
                ("legacy-1", "历史报告一", "DATA_REVIEW", "{}",
                 "2026-09-19T01:00:00+00:00", "2026-09-19T01:00:00+00:00", 0),
                ("legacy-2", "历史报告二", "DATA_REVIEW", "{}",
                 "2026-09-19T02:00:00+00:00", "2026-09-19T02:00:00+00:00", 0),
            ],
        )
        connection.execute(
            "DELETE FROM app_migrations WHERE `key`=%s",
            (REPORT_NUMBER_MIGRATION,),
        )
    ensure_report_number_schema(database)

    reports = {item["id"]: item for item in database.list_reports()}
    current = database.create_report(
        report_item("current", "2026-09-19T03:00:00+00:00")
    )

    assert reports["legacy-1"]["report_number"] == "JYD-20260919-001"
    assert reports["legacy-2"]["report_number"] == "JYD-20260919-002"
    assert current["report_number"] == "JYD-20260919-003"


def test_concurrent_report_creation_keeps_numbers_unique(tmp_path) -> None:
    database = make_test_database(tmp_path)
    timestamp = "2026-09-19T04:00:00+00:00"
    barrier = threading.Barrier(8)
    numbers: list[str] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        try:
            barrier.wait()
            report = database.create_report(report_item(f"concurrent-{index}", timestamp))
            with lock:
                numbers.append(report["report_number"])
        except Exception as error:  # noqa: BLE001 - 汇总所有并发错误供断言定位
            with lock:
                errors.append(repr(error))

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(numbers) == [f"JYD-20260919-{index:03d}" for index in range(1, 9)]
