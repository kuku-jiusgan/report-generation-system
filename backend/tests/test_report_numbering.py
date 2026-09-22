import threading

from backend.app.services.report_numbering import (
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


def test_report_number_schema_check_keeps_existing_number_unchanged(tmp_path) -> None:
    database = make_test_database(tmp_path)
    existing = database.create_report(report_item("existing", "2026-09-19T01:00:00+00:00"))

    ensure_report_number_schema(database)

    assert database.get_report(existing["id"])["report_number"] == existing["report_number"]


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
