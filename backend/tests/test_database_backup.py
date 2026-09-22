import gzip
import io
from datetime import datetime
from pathlib import Path

import pytest

from backend.app.config import PROJECT_ROOT, Settings
from backend.app.database_backup import DatabaseBackupError, backup_database


def backup_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_database="backup_test",
        mysql_user="backup_user",
        mysql_password='secret#with"quotes\\slashes',
    )


def test_database_backup_is_compressed_atomic_and_hides_password(tmp_path, monkeypatch) -> None:
    settings = backup_settings(tmp_path)
    observed_credentials = ""
    observed_command: list[str] = []

    class SuccessfulDump:
        stdout = io.BytesIO(b"CREATE TABLE example (id INT);\n")

        def wait(self):
            return 0

        def kill(self):
            raise AssertionError("成功备份不应终止 mysqldump")

    def dump(command, stdout, stderr):
        nonlocal observed_credentials, observed_command
        observed_command = command
        credentials_path = Path(command[1].split("=", 1)[1])
        observed_credentials = credentials_path.read_text(encoding="utf-8")
        return SuccessfulDump()

    monkeypatch.setattr("backend.app.database_backup.shutil.which", lambda _: "/usr/bin/mysqldump")
    monkeypatch.setattr("backend.app.database_backup.subprocess.Popen", dump)

    result = backup_database(settings, datetime(2026, 9, 22, 0, 0))

    assert result.name == "backup_test-20260922-000000-000000.sql.gz"
    assert gzip.decompress(result.read_bytes()) == b"CREATE TABLE example (id INT);\n"
    assert settings.mysql_password not in " ".join(observed_command)
    assert 'password="secret#with\\"quotes\\\\slashes"' in observed_credentials
    assert not list(settings.database_backups_dir.glob(".*"))


def test_database_backup_failure_removes_temporary_files(tmp_path, monkeypatch) -> None:
    settings = backup_settings(tmp_path)

    class FailedDump:
        stdout = io.BytesIO(b"partial dump")

        def wait(self):
            return 2

        def kill(self):
            raise AssertionError("正常退出的 mysqldump 不应被终止")

    def fail(command, stdout, stderr):
        stderr.write("连接失败".encode())
        return FailedDump()

    monkeypatch.setattr("backend.app.database_backup.shutil.which", lambda _: "/usr/bin/mysqldump")
    monkeypatch.setattr("backend.app.database_backup.subprocess.Popen", fail)

    with pytest.raises(DatabaseBackupError, match="连接失败"):
        backup_database(settings)

    assert list(settings.database_backups_dir.iterdir()) == []


def test_database_backup_timer_runs_at_midnight_and_catches_missed_run() -> None:
    timer = (PROJECT_ROOT / "deploy" / "report-generation-backup.timer").read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* 00:00:00" in timer
    assert "Persistent=true" in timer
