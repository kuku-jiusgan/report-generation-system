"""报告生成历史：每"生成"一次留一条，打开报告补渲染不算一次生成。"""

from typing import Any


class _Recorder:
    """替身：只记录写进历史的内容，不碰数据库。"""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def create_generation(self, item: dict[str, Any]) -> dict[str, Any]:
        self.entries.append(item)
        return item

    def phases(self) -> list[str]:
        return [entry["generation_context"]["phase"] for entry in self.entries]


def _record(recorder: _Recorder, report_id: str, data: dict[str, Any], phase: str,
            actor: str = "", status: str = "SUCCESS", output_name: str = "",
            error: str = "") -> str:
    """与 main.record_generation 相同的落库形状，隔离掉 FastAPI 依赖。"""
    entry = {
        "id": f"gen-{len(recorder.entries)}", "report_id": report_id,
        "generated_by": actor or None, "status": status,
        "output_name": output_name, "error_message": error,
        "generation_snapshot": {"resolved_data": data,
                                "field_sources": data.get("field_sources", {}),
                                "original_values": data.get("original_values", {}),
                                "warnings": data.get("warnings", [])},
        "generation_context": {"phase": phase,
                               "template_name": data.get("template_name", ""),
                               "template_version": data.get("template_version", ""),
                               "template_revision": data.get("template_revision", "")},
    }
    recorder.create_generation(entry)
    return entry["id"]


DATA = {
    "project_name": "某某分析报告",
    "field_sources": {"samples.batchNo": {"type": "EXCEL"}},
    "original_values": {"samples.batchNo": "A-1"},
    "warnings": ["单值字段提取到 2 个值"],
    "template_name": "验证报告模板", "template_version": "V1", "template_revision": "abc123",
}


def test_snapshot_carries_the_extracted_field_content() -> None:
    recorder = _Recorder()
    _record(recorder, "r1", DATA, "创建报告", "u1")

    snapshot = recorder.entries[0]["generation_snapshot"]
    assert snapshot["resolved_data"] == DATA
    assert snapshot["field_sources"] == {"samples.batchNo": {"type": "EXCEL"}}
    assert snapshot["original_values"] == {"samples.batchNo": "A-1"}
    assert snapshot["warnings"] == ["单值字段提取到 2 个值"]
    assert recorder.entries[0]["generated_by"] == "u1"


def test_context_records_which_action_produced_it() -> None:
    recorder = _Recorder()
    for phase in ("创建报告", "载入 LIMS 实验记录", "更换数据源（EXCEL）", "重建 Word", "导出 Word"):
        _record(recorder, "r1", DATA, phase, "u1")

    assert recorder.phases() == ["创建报告", "载入 LIMS 实验记录", "更换数据源（EXCEL）",
                                 "重建 Word", "导出 Word"]
    assert recorder.entries[0]["generation_context"]["template_revision"] == "abc123"


def test_failed_generation_is_recorded_with_the_reason() -> None:
    recorder = _Recorder()
    _record(recorder, "r1", DATA, "载入 LIMS 实验记录", "u1", status="FAILED", error="模板编译失败")

    assert recorder.entries[0]["status"] == "FAILED"
    assert recorder.entries[0]["error_message"] == "模板编译失败"
    # 失败也要留下当时的字段快照，便于对照是哪份数据没填上
    assert recorder.entries[0]["generation_snapshot"]["resolved_data"] == DATA


def test_render_without_a_phase_records_nothing() -> None:
    """打开报告 / 打开编辑器时为补齐缺失文件而渲染，不传阶段，就不算一次生成。"""
    recorder = _Recorder()
    phase = ""
    if phase:
        _record(recorder, "r1", DATA, phase)

    assert recorder.entries == []
