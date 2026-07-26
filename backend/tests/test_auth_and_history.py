import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi import HTTPException

from app.auth import AuthManager
from app.config import Settings
from app.database import Database, now_iso


class AuthenticationAndHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(
            data_dir=root / "data", template_path=root / "template.docx",
            bootstrap_admin_username="rootadmin", bootstrap_admin_password="Admin@123456",
        )
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path)
        self.database.initialize()
        self.auth = AuthManager(self.database, self.settings)
        self.admin_id = self.auth.bootstrap()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_report_user(self, username: str = "reporter") -> dict:
        return self.database.create_user({
            "id": uuid.uuid4().hex, "username": username, "display_name": "报告用户",
            "password_hash": self.auth.hash_password("Reporter@123"), "role_code": "REPORT_USER",
            "must_change_password": False,
        })

    def test_password_session_and_disabled_user(self) -> None:
        user = self.auth.authenticate("rootadmin", "Admin@123456")
        self.assertIsNotNone(user)
        self.assertIsNone(self.auth.authenticate("rootadmin", "wrong-password"))
        token, _ = self.auth.issue_session(user["id"])
        current = self.auth.current_user(token)
        self.assertEqual("SUPER_ADMIN", current["role_code"])
        self.database.update_user(user["id"], enabled=0)
        with self.assertRaises(HTTPException) as error:
            self.auth.current_user(token)
        self.assertEqual(401, error.exception.status_code)

    def test_report_owner_filtering(self) -> None:
        first = self.create_report_user("first")
        second = self.create_report_user("second")
        timestamp = now_iso()
        for owner in (first, second):
            self.database.create_report({
                "id": uuid.uuid4().hex, "title": owner["username"], "status": "DATA_REVIEW",
                "resolved_data": {}, "created_at": timestamp, "updated_at": timestamp,
                "created_by": owner["id"], "updated_by": owner["id"],
            })
        self.assertEqual(1, len(self.database.list_reports(first["id"])))
        self.assertEqual("first", self.database.list_reports(first["id"])[0]["title"])

    def test_generation_history_keeps_each_attempt(self) -> None:
        user = self.create_report_user()
        timestamp = now_iso()
        report = self.database.create_report({
            "id": uuid.uuid4().hex, "title": "历史报告", "status": "DATA_REVIEW",
            "resolved_data": {"report_no": "R-001"}, "created_at": timestamp, "updated_at": timestamp,
            "created_by": user["id"], "updated_by": user["id"],
        })
        version = self.database.create_version(report["id"], report["resolved_data"], "生成")
        self.database.create_generation({
            "id": "success", "report_id": report["id"], "version_id": version["id"],
            "generated_by": user["id"], "status": "SUCCESS", "output_name": "one.docx",
        })
        self.database.create_generation({
            "id": "failed", "report_id": report["id"], "version_id": version["id"],
            "generated_by": user["id"], "status": "FAILED", "error_message": "模板错误",
        })
        page = self.database.list_generations(query="R-001")
        self.assertEqual(2, page["total"])
        self.assertEqual({"SUCCESS", "FAILED"}, {item["status"] for item in page["items"]})

    def test_report_lifecycle_fields_and_cleanup_preserve_users(self) -> None:
        user = self.create_report_user("lifecycle")
        timestamp = now_iso()
        report = self.database.create_report({
            "id": uuid.uuid4().hex, "title": "任务", "status": "EDITING",
            "resolved_data": {}, "created_at": timestamp, "updated_at": timestamp,
            "created_by": user["id"], "updated_by": user["id"],
            "word_edit_locked": True, "word_edited_at": timestamp,
        })
        self.assertTrue(report["word_edit_locked"])
        self.assertEqual(timestamp, report["word_edited_at"])

        self.database.clear_report_test_data()
        self.assertEqual([], self.database.list_reports(user["id"]))
        self.assertIsNotNone(self.database.get_user(user["id"]))
        self.database.mark_migration_applied("lifecycle-test")
        self.database.mark_migration_applied("lifecycle-test")
        self.assertTrue(self.database.migration_applied("lifecycle-test"))


if __name__ == "__main__":
    unittest.main()
