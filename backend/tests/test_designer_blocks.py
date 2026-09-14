from pathlib import Path

from backend.app.admin_api import create_admin_router
from backend.app.config import Settings
from backend.app.services.designer_blocks import designer_blocks


class DesignerRepositoryStub:
    database = object()

    @staticmethod
    def list_mappings() -> list[dict]:
        return []

    @staticmethod
    def active_workspace() -> None:
        return None

    @staticmethod
    def standard_field_catalog() -> dict:
        return {
            "chapters": [{
                "id": 71, "code": "7.1", "title": "系统适用性",
                "fields": [{"fieldCode": "method.testMethod", "label": "试验方法", "enabled": True}],
                "children": [],
            }],
            "groups": [{
                "groupCode": "systemSuitability", "label": "系统适用性结果",
                "chapterIds": [71], "fields": [], "enabled": True,
            }],
        }

    @staticmethod
    def list_template_chapters() -> list[dict]:
        return [{
            "id": 71, "parentId": None, "code": "7.1", "title": "系统适用性",
            "orderNo": 1, "enabled": True,
        }]

    @staticmethod
    def list_table_rules() -> list[dict]:
        return []


class AuthStub:
    @staticmethod
    def admin_route_guard() -> dict:
        return {}


def test_designer_blocks_include_direct_fields_and_groups_without_mixing() -> None:
    direct_field = {"fieldCode": "method.testMethod", "label": "试验方法", "enabled": True}
    grouped_field = {"fieldCode": "systemSuitability.peakArea", "label": "峰面积", "enabled": True}
    chapters = [{
        "id": 71, "code": "7.1", "title": "系统适用性", "fields": [direct_field], "children": [],
    }]
    groups = [{
        "groupCode": "systemSuitability", "label": "系统适用性结果",
        "chapterIds": [71], "fields": [grouped_field], "enabled": True,
    }]
    mappings = [{
        "id": 11, "chapterId": 71, "standardFieldCode": "method.testMethod",
        "controlTag": "cc.method", "sourceType": "SYSTEM",
    }, {
        "id": 12, "chapterId": 71, "standardFieldCode": "systemSuitability.peakArea",
        "controlTag": "cc.peak-area", "sourceType": "LIMS",
    }]

    blocks, groups_by_chapter = designer_blocks(chapters, groups, mappings, {}, [])

    assert groups_by_chapter[71] == groups
    assert [block["title"] for block in blocks[71]] == ["章节字段", "系统适用性结果"]
    assert [field["fieldCode"] for field in blocks[71][0]["standardFields"]] == ["method.testMethod"]
    assert blocks[71][0]["mappingIds"] == [11]
    assert [field["fieldCode"] for field in blocks[71][1]["standardFields"]] == [
        "systemSuitability.peakArea",
    ]
    assert blocks[71][1]["mappingIds"] == [12]


def test_designer_blocks_include_direct_fields_from_nested_chapters() -> None:
    chapters = [{
        "id": 7, "fields": [], "children": [{
            "id": 71, "fields": [{"fieldCode": "method.testMethod", "label": "试验方法"}],
            "children": [],
        }],
    }]

    blocks, _ = designer_blocks(chapters, [], [], {}, [])

    assert 7 not in blocks
    assert blocks[71][0]["standardFields"][0]["label"] == "试验方法"


def test_designer_route_includes_chapter_fields_from_standard_catalog(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", template_path=tmp_path / "template.docx")
    router = create_admin_router(DesignerRepositoryStub(), settings, AuthStub())
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/v1/admin/designer")

    payload = endpoint()

    chapter = payload["chapters"][0]
    assert chapter["code"] == "7.1"
    assert [block["title"] for block in chapter["blocks"]] == ["章节字段", "系统适用性结果"]
    assert chapter["blocks"][0]["standardFields"][0]["label"] == "试验方法"
