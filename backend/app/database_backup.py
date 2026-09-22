import gzip
import logging
import os
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import tempfile

from .config import Settings, get_settings


LOGGER = logging.getLogger(__name__)


class DatabaseBackupError(RuntimeError):
    pass


def mysql_option_value(value: str) -> str:
    if "\x00" in value or "\n" in value or "\r" in value:
        raise DatabaseBackupError("MySQL 连接配置包含不支持的控制字符")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_credentials_file(settings: Settings, directory: Path) -> Path:
    content = (
        "[client]\n"
        f"host={mysql_option_value(settings.mysql_host)}\n"
        f"port={settings.mysql_port}\n"
        f"user={mysql_option_value(settings.mysql_user)}\n"
        f"password={mysql_option_value(settings.mysql_password)}\n"
    )
    descriptor, name = tempfile.mkstemp(prefix=".mysql-backup-", suffix=".cnf", dir=directory)
    credentials_path = Path(name)
    try:
        with open(descriptor, "w", encoding="utf-8", closefd=True) as credentials:
            credentials.write(content)
    except Exception:
        credentials_path.unlink(missing_ok=True)
        raise
    return credentials_path


def dump_command(executable: str, credentials_path: Path, database: str) -> list[str]:
    return [
        executable,
        f"--defaults-extra-file={credentials_path}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--events",
        "--triggers",
        "--hex-blob",
        "--default-character-set=utf8mb4",
        "--no-tablespaces",
        "--databases",
        database,
    ]


def run_dump(command: list[str], output_path: Path) -> None:
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        except OSError as error:
            raise DatabaseBackupError(f"无法启动 mysqldump：{error}") from error
        if process.stdout is None:
            process.kill()
            process.wait()
            raise DatabaseBackupError("无法读取 mysqldump 输出")
        try:
            with process.stdout, gzip.open(output_path, "wb", compresslevel=6) as output:
                shutil.copyfileobj(process.stdout, output)
        except Exception:
            process.kill()
            process.wait()
            raise
        returncode = process.wait()
        errors.seek(0)
        detail = errors.read().decode("utf-8", errors="replace").strip()
    if returncode == 0:
        return
    raise DatabaseBackupError(f"mysqldump 执行失败：{detail or f'退出码 {returncode}'}")


def backup_database(settings: Settings, moment: datetime | None = None) -> Path:
    executable = shutil.which("mysqldump")
    if not executable:
        raise DatabaseBackupError("未找到 mysqldump，请先安装 MySQL 客户端工具")
    backup_dir = settings.database_backups_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (moment or datetime.now().astimezone()).strftime("%Y%m%d-%H%M%S-%f")
    final_path = backup_dir / f"{settings.mysql_database}-{timestamp}.sql.gz"
    if final_path.exists():
        raise DatabaseBackupError(f"备份文件已存在：{final_path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".database-backup-", suffix=".sql.gz.tmp", dir=backup_dir,
    )
    temporary_path = Path(temporary_name)
    os.close(descriptor)
    temporary_path.chmod(0o600)
    credentials_path: Path | None = None
    try:
        credentials_path = write_credentials_file(settings, backup_dir)
        run_dump(dump_command(executable, credentials_path, settings.mysql_database), temporary_path)
        temporary_path.replace(final_path)
        return final_path
    finally:
        temporary_path.unlink(missing_ok=True)
        if credentials_path:
            credentials_path.unlink(missing_ok=True)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        settings = get_settings()
        backup_path = backup_database(settings)
    except DatabaseBackupError as error:
        LOGGER.error("数据库备份失败：%s", error)
        return 1
    except Exception:
        LOGGER.exception("数据库备份发生未预期错误")
        return 1
    LOGGER.info("数据库备份完成 database=%s path=%s", settings.mysql_database, backup_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
