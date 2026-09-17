"""段内字段的取值预览和数据溯源要能查到证据。

段（project、document 以及基数为 ONE 的编组）整段存在 lims_experiments.sections_json，
不像 samples 那样一行一条存在 lims_standard_records。字段目录里的存储位置声明只被预览和
溯源用来决定去哪张表捞证据；声明成记录表时，段内字段永远查不到任何行。

这里同时锁住三件事：段列能按段名和键名取到值、标量列的预览在 MySQL 上不再报 1064、
以及段列里没有该键的实验不算命中。
"""

import tempfile
import unittest
from pathlib import Path

from backend.app.repositories.lims_instances import SECTION_COLUMN, collection_storage
from backend.app.services.system_field_groups import save_system_field_group
from backend.tests.database_helpers import make_test_database


def _raw(instance_id: str, client_name: str = "") -> dict:
    project = {"id": "XM-1", "name": "项目甲"}
    if client_name:
        project["clientName"] = client_name
    return {"instanceId": instance_id, "projectId": "XM-1", "title": f"实验 {instance_id}",
            "version": 1, "createdBy": "张三", "createdTime": "2026-09-01T10:00:00",
            "project": project, "document": {"code": instance_id, "version": "1"}}


def _normalized(raw: dict) -> dict:
    return {"project": dict(raw["project"]), "document": dict(raw["document"]),
            "approval": [], "unmatched": [],
            "instances": [{"instanceId": raw["instanceId"], "title": raw["title"],
                           "projectId": "XM-1", "version": 1}]}


CLIENT_FIELD = {
    "fieldCode": "uncategorized.field_087", "label": "客户名称", "collectionCode": "project",
    "dbTable": "lims_experiments", "dbColumn": SECTION_COLUMN, "jsonKey": "clientName",
}
TITLE_FIELD = {
    "fieldCode": "project.name", "label": "文件标题", "collectionCode": "project",
    "dbTable": "lims_experiments", "dbColumn": SECTION_COLUMN, "jsonKey": "",
}


class CollectionStorageTest(unittest.TestCase):
    """存储位置由集合的落库方式推出来，字段目录里不再存声明。"""

    def test_record_collections_live_in_the_standard_records_table(self) -> None:
        self.assertEqual(collection_storage("samples", "MANY"), ("lims_standard_records", "data_json"))
        self.assertEqual(collection_storage("approval", "MANY"), ("lims_standard_records", "data_json"))

    def test_single_value_groups_live_in_the_section_column(self) -> None:
        self.assertEqual(collection_storage("project", "ONE"), ("lims_experiments", SECTION_COLUMN))
        self.assertEqual(collection_storage("Conclusion", "ONE"), ("lims_experiments", SECTION_COLUMN))

    def test_collections_that_are_never_persisted_have_no_storage(self) -> None:
        """溶液视图是读取时从 solutions 派生的，没有自己的记录行，也就没有证据可查。"""
        self.assertIsNone(collection_storage("specificitySolutions", "MANY"))
        self.assertEqual(
            collection_storage("custom", "MANY"), ("lims_standard_records", "data_json"),
        )
        self.assertIsNone(collection_storage("custom", ""))

    def test_record_collections_win_over_cardinality(self) -> None:
        """conclusions 既是记录型集合又是多行编组，落库方式以记录表为准。"""
        self.assertEqual(collection_storage("conclusions", "MANY"), ("lims_standard_records", "data_json"))


class SectionFieldEvidenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.database = make_test_database(Path(self._directory.name))
        self.database.create_lims_import({
            "id": "imp1", "file_name": "Oracle 查询：XM-1", "stored_name": "", "size": 0,
            "summary": {}, "created_at": "2026-09-01T10:00:00",
        })

    def _store(self, instance_id: str, client_name: str = "") -> None:
        raw = _raw(instance_id, client_name)
        self.database.replace_lims_instance("imp1", raw, _normalized(raw), [])

    def test_section_field_preview_reads_the_section_column(self) -> None:
        self._store("EXP-1", "某某医药研究院有限公司")
        preview = self.database.preview_lims_field(CLIENT_FIELD)
        self.assertTrue(preview["storageSupported"])
        self.assertEqual(preview["total"], 1)
        self.assertEqual(preview["items"][0]["value"], "某某医药研究院有限公司")
        self.assertEqual(preview["items"][0]["instanceId"], "EXP-1")
        self.assertEqual(preview["items"][0]["fileName"], "Oracle 查询：XM-1")

    def test_experiments_without_the_key_are_not_counted_as_hits(self) -> None:
        self._store("EXP-1", "某某医药研究院有限公司")
        self._store("EXP-2")
        preview = self.database.preview_lims_field(CLIENT_FIELD)
        self.assertEqual(preview["total"], 1)
        self.assertEqual([item["instanceId"] for item in preview["items"]], ["EXP-1"])

    def test_empty_json_key_falls_back_to_the_field_code_tail(self) -> None:
        """`project.name` 的键名留空，不回退就会把整个 project 段当成取值返回。"""
        self._store("EXP-1", "某某医药研究院有限公司")
        preview = self.database.preview_lims_field(TITLE_FIELD)
        self.assertTrue(preview["storageSupported"])
        self.assertEqual(preview["items"][0]["value"], "项目甲")

    def test_catalog_derives_storage_instead_of_storing_it(self) -> None:
        # 集合的基数只在编组里定义，推导要用它，所以编组得先存在
        save_system_field_group(self.database, {"groupCode": "project", "label": "项目信息",
                                               "cardinality": "ONE"})
        self.database.upsert_lims_field({
            "fieldCode": "uncategorized.field_087", "label": "客户名称", "groupCode": "project",
            "collectionCode": "project", "dataType": "string", "cardinality": "ONE",
            "jsonKey": "clientName", "legacyJsonPath": "$.project.clientName",
            "description": "", "outputFormat": "", "defaultValue": "",
            "validationRegex": "", "orderNo": 0, "enabled": True,
        })
        field = self.database.get_lims_field("uncategorized.field_087")
        self.assertEqual(field["dbTable"], "lims_experiments")
        self.assertEqual(field["dbColumn"], SECTION_COLUMN)

    def test_section_field_instance_source_finds_evidence(self) -> None:
        self._store("EXP-1", "某某医药研究院有限公司")
        source = self.database.get_lims_field_instance_source(CLIENT_FIELD, "imp1", "EXP-1")
        groups = source["source"]["unitGroups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["recognizedItems"][0]["value"], "某某医药研究院有限公司")

    def test_fields_without_storage_are_refused(self) -> None:
        """推导不出存储位置的字段直接答"不支持"，不去猜一张表。"""
        self._store("EXP-1", "某某医药研究院有限公司")
        preview = self.database.preview_lims_field({**CLIENT_FIELD, "dbTable": "", "dbColumn": ""})
        self.assertFalse(preview["storageSupported"])
        self.assertEqual(preview["total"], 0)


if __name__ == "__main__":
    unittest.main()
