"""编组的数组结构由层级配置生成：一层是老的扁平形状，两层要按分组切分。"""

import pytest

from backend.app.services.payload_paths import (
    PayloadPathError,
    first_payload_value,
    path_depth,
    read_payload_path,
    set_payload_path,
)
from backend.app.services.system_field_group_levels import (
    ARRAY, OBJECT, field_path_for, json_path_for, structure_preview,
)


def test_flat_collection_keeps_the_old_shape() -> None:
    payload: dict = {}
    set_payload_path(payload, "$.samples[*].batchNo", ["A", "B"])
    set_payload_path(payload, "$.samples[*].name", ["甲", "乙"])

    assert payload == {"samples": [{"batchNo": "A", "name": "甲"}, {"batchNo": "B", "name": "乙"}]}


def test_scalar_path_writes_a_plain_value() -> None:
    payload: dict = {}
    set_payload_path(payload, "$.project.name", "验证报告")

    assert payload == {"project": {"name": "验证报告"}}


def test_nested_levels_split_a_flat_list_by_group() -> None:
    payload: dict = {}
    set_payload_path(payload, "$.suitability[*].impurityName", ["甲", "乙"])
    set_payload_path(payload, "$.suitability[*].summary.peakAreaRsd", [1.4, 0.3])
    set_payload_path(payload, "$.suitability[*].injections[*].retentionTime", [1, 2, 3, 4, 5, 6])

    assert payload["suitability"] == [
        {"impurityName": "甲", "summary": {"peakAreaRsd": 1.4},
         "injections": [{"retentionTime": 1}, {"retentionTime": 2}, {"retentionTime": 3}]},
        {"impurityName": "乙", "summary": {"peakAreaRsd": 0.3},
         "injections": [{"retentionTime": 4}, {"retentionTime": 5}, {"retentionTime": 6}]},
    ]


def test_detail_level_needs_the_group_level_written_first() -> None:
    with pytest.raises(PayloadPathError, match="外层数组还没有建立"):
        set_payload_path({}, "$.suitability[*].injections[*].retentionTime", [1, 2])


def test_values_that_do_not_divide_evenly_are_rejected() -> None:
    payload = {"suitability": [{}, {}, {}]}
    with pytest.raises(PayloadPathError, match="无法平均分给 3 个分组"):
        set_payload_path(payload, "$.suitability[*].injections[*].x", [1, 2, 3, 4])


def test_write_order_is_driven_by_array_depth() -> None:
    paths = ["$.a[*].b[*].c", "$.a[*].d", "$.e"]
    assert sorted(paths, key=path_depth) == ["$.e", "$.a[*].d", "$.a[*].b[*].c"]


def test_field_path_is_derived_from_the_level() -> None:
    assert field_path_for("", "", "impurityName") == "impurityName"
    assert field_path_for("summary", OBJECT, "peakAreaRsd") == "summary.peakAreaRsd"
    assert field_path_for("injections", ARRAY, "retentionTime") == "injections[*].retentionTime"


def test_json_path_combines_the_collection_and_the_field_path() -> None:
    assert json_path_for("$.suitability", "MANY", "summary.peakAreaRsd") == \
        "$.suitability[*].summary.peakAreaRsd"
    assert json_path_for("$.project", "ONE", "name") == "$.project.name"


def test_structure_preview_mirrors_the_configured_levels() -> None:
    levels = [{"levelKey": "summary", "kind": OBJECT}, {"levelKey": "injections", "kind": ARRAY}]
    fields = [
        {"fieldCode": "g.impurityName", "jsonKey": "impurityName", "levelKey": "", "label": "杂质名称"},
        {"fieldCode": "g.peakAreaRsd", "jsonKey": "peakAreaRsd", "levelKey": "summary", "label": "峰面积 RSD"},
        {"fieldCode": "g.peakArea", "jsonKey": "peakArea", "levelKey": "injections", "label": "峰面积"},
    ]

    assert structure_preview(levels, fields) == {
        "impurityName": "杂质名称",
        "summary": {"peakAreaRsd": "峰面积 RSD"},
        "injections": [{"peakArea": "峰面积"}],
    }


def test_read_payload_path_flattens_nested_array_levels() -> None:
    payload = {"samples": [
        {"batchNo": "B1", "injections": [{"sampleName": "样品甲"}]},
        {"batchNo": "B2", "injections": [{"sampleName": "样品乙"}]},
    ]}

    path = "$.samples[*].injections[*].sampleName"

    assert read_payload_path(payload, path) == ["样品甲", "样品乙"]
    assert first_payload_value(payload, path) == "样品甲"
