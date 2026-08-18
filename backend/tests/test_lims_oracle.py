import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.schemas import QueryLimsRequest
from backend.app.services.lims_parser import EXPECTED_PREFIX
from backend.app.services.lims_oracle import LIMS_PROJECT_SQL, query_lims_project
from backend.app.services.lims_files import absolute_lims_file_urls


class FakeCursor:
    def __init__(self, values, source_names=None):
        self.description = [(name,) for name in [*EXPECTED_PREFIX, *[f"COL{i}" for i in range(7, 49)]]]
        self.values = values
        self.executed_sql = ""
        self.parameters = {}
        self.source_names = source_names or []
        self.reading_source_names = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, **parameters):
        self.executed_sql = sql
        self.parameters = parameters
        self.reading_source_names = "U_DEPTEPT" in sql

    def fetchall(self):
        return self.source_names if self.reading_source_names else self.values


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def close(self):
        self.closed = True


class LimsOracleTests(unittest.TestCase):
    def test_query_uses_bound_project_id_and_parses_instances(self):
        row = [None] * 49
        row[0:8] = ["U1", "I1", None, "Section", "实验名称：含量测定", None, None, 1]
        row[22] = 3
        row[24] = "tester"
        row[46] = "XM2024108"
        row[47] = "EPT1"
        cursor = FakeCursor([tuple(row)], [("EPT1", "真实实验名称")])
        connection = FakeConnection(cursor)
        settings = Settings(
            lims_sql_enabled=True,
            lims_sql_dsn="db:1521/service",
            lims_sql_user="read",
            lims_sql_password="secret",
        )

        with patch("backend.app.services.lims_oracle.oracledb.connect", return_value=connection) as connect:
            summary, instances = query_lims_project(settings, "XM2024108")

        self.assertEqual({"source_0": "EPT1"}, cursor.parameters)
        self.assertNotIn("XM2024108", LIMS_PROJECT_SQL)
        self.assertEqual(1, summary["instanceCount"])
        self.assertEqual("真实实验名称", instances[0]["title"])
        self.assertTrue(connection.closed)
        connect.assert_called_once_with(
            user="read", password="secret", dsn="db:1521/service", tcp_connect_timeout=10.0,
        )

    def test_project_id_rejects_sql_text(self):
        with self.assertRaises(ValidationError):
            QueryLimsRequest(project_id="XM2024108' OR 1=1 --")

    def test_relative_lims_file_urls_are_absolutized_recursively(self):
        payload = {
            "imageUrls": ["/files/open/20260616/a/image.png", "https://cdn.example/a.png"],
            "html": '<img src="/files/open/20260616/b/image.png">',
        }

        result = absolute_lims_file_urls(payload, "http://192.168.2.17/")

        self.assertEqual(result["imageUrls"][0], "http://192.168.2.17/files/open/20260616/a/image.png")
        self.assertEqual(result["imageUrls"][1], "https://cdn.example/a.png")
        self.assertIn('src="http://192.168.2.17/files/open/20260616/b/image.png"', result["html"])


if __name__ == "__main__":
    unittest.main()
