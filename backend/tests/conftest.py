"""测试一律连独立的测试库，绝不允许碰生产库。

`Settings` 里 mysql_* 有默认值，测试构造 `Settings(data_dir=临时目录, ...)` 时只覆盖了
文件路径，数据库仍然落到 .env 指向的生产库。而 `clear_report_test_data()` 这类用例会
无条件 DELETE reports / report_versions / report_generation_history 等表——真实数据
会被整张清掉。这里在导入任何应用代码之前改写环境变量，并在库名仍是生产库时直接中止。
"""

import os

import pymysql
import pytest


PRODUCTION_DATABASE = "report_generation_system"
TEST_DATABASE = os.environ.get("REPORT_TEST_MYSQL_DATABASE", f"{PRODUCTION_DATABASE}_test")

# 必须在 backend.app.config 被导入前设置：环境变量优先级高于 .env
os.environ["REPORT_MYSQL_DATABASE"] = TEST_DATABASE


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database() -> None:
    """确保测试库存在，并复核应用读到的库名确实不是生产库。"""
    from backend.app.config import get_settings

    settings = get_settings()
    if settings.mysql_database == PRODUCTION_DATABASE:
        pytest.exit(
            f"测试被指向了生产库 {PRODUCTION_DATABASE}，已中止。"
            f"测试会清空 reports / report_versions / report_generation_history 等表。",
            returncode=2,
        )
    try:
        # 连接凭据取自应用配置（含 .env），只把库名换成测试库
        connection = pymysql.connect(
            host=settings.mysql_host, port=settings.mysql_port,
            user=settings.mysql_user, password=settings.mysql_password, charset="utf8mb4",
        )
    except pymysql.err.OperationalError as error:
        pytest.exit(f"无法连接 MySQL 以准备测试库：{error}", returncode=2)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            cursor.execute(f"SHOW TABLES FROM `{PRODUCTION_DATABASE}`")
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                cursor.execute(
                    f"CREATE TABLE IF NOT EXISTS `{settings.mysql_database}`.`{table}` "
                    f"LIKE `{PRODUCTION_DATABASE}`.`{table}`"
                )
        connection.commit()


@pytest.fixture(autouse=True)
def clean_test_database() -> None:
    """Keep tests isolated while retaining the production schema shape."""
    from backend.app.config import get_settings

    settings = get_settings()
    connection = pymysql.connect(
        host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password,
        database=settings.mysql_database, charset="utf8mb4", autocommit=False,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                cursor.execute(f"DELETE FROM `{table}`")
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        connection.commit()
    finally:
        connection.close()
