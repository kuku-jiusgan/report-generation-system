"""归一化载荷里不成行的段必须整段存下来，不能只留写死的那几个键。

客户名称走 `$.project.clientName`：原始数据里有值，提取规则也配对了，但落库时
project 段只被投影成 project_id/project_name 两列，clientName 在写入那一刻就丢了，
生成报告时取到空值。这里锁住整段往返。
"""

import tempfile
import unittest
from pathlib import Path

from backend.app.services.lims_normalizer import COLLECTION_ORDER
from backend.tests.database_helpers import make_test_database


RAW = {
    "instanceId": "T0001",
    "projectId": "XM9999",
    "title": "某物中某杂质分析方法验证",
    "version": 1,
    "createdBy": "张三",
    "createdTime": "2026-09-01T10:00:00",
    "project": {"id": "XM9999", "name": "某物中某杂质分析方法验证", "clientName": "某某医药研究院有限公司"},
    "document": {"code": "T0001", "version": "1"},
}


def _normalized() -> dict:
    return {
        "project": dict(RAW["project"]),
        "document": dict(RAW["document"]),
        "approval": [],
        "instances": [{"instanceId": "T0001", "title": RAW["title"],
                       "projectId": "XM9999", "version": 1}],
        "samples": [{"sampleName": "某物", "clientName": "某某医药研究院有限公司"}],
        "unmatched": [],
    }


class LimsSingularSectionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.database = make_test_database(Path(self._directory.name))
        self.database.create_lims_import({
            "id": "imp1", "file_name": "t.json", "stored_name": "t.json",
            "size": 1, "summary": {}, "created_at": "2026-09-01T10:00:00",
        })

    def _round_trip(self) -> dict:
        self.database.replace_lims_instance("imp1", RAW, _normalized(), COLLECTION_ORDER)
        payload = self.database.get_lims_normalized_payload("imp1", "T0001")
        self.assertIsNotNone(payload)
        return payload

    def test_project_section_keeps_every_key(self) -> None:
        payload = self._round_trip()
        self.assertEqual(payload["project"], RAW["project"])
        self.assertEqual(payload["project"]["clientName"], "某某医药研究院有限公司")

    def test_document_section_survives_round_trip(self) -> None:
        self.assertEqual(self._round_trip()["document"], RAW["document"])

    def test_extra_singular_sections_survive_round_trip(self) -> None:
        """基数为 ONE 的编组段和 project 走同一条路，不需要再为每个段加代码。"""
        normalized = _normalized()
        normalized["Conclusion"] = {"text": "符合规定"}
        self.database.replace_lims_instance("imp1", RAW, normalized, COLLECTION_ORDER)
        payload = self.database.get_lims_normalized_payload("imp1", "T0001")
        self.assertEqual(payload["Conclusion"], {"text": "符合规定"})

    def test_record_collections_still_come_back_as_rows(self) -> None:
        samples = self._round_trip()["samples"]
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["sampleName"], "某物")


if __name__ == "__main__":
    unittest.main()
