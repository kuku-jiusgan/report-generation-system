"""启动自愈：首次迁移完成后，再次启动只补缺失，不得回滚管理员的修改。"""
from pathlib import Path

from backend.app.database import Database
from backend.app.services.excel_rule_defaults import EXCEL_FIELD_PATHS, ensure_excel_field_rules
from backend.app.services.rule_admin import RuleAdminRepository
from backend.app.services.system_field_defaults import _field_code

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_startup_seed_keeps_admin_changes_after_first_run(tmp_path: Path) -> None:
    database = Database(tmp_path / "seed.db")
    database.initialize()
    repository = RuleAdminRepository(database, PROJECT_ROOT / "mapping" / "template-mapping.json")
    # 首次启动：播种 + 一次性遗留迁移
    repository.seed()
    ensure_excel_field_rules(database)

    # 管理员修改一：Excel 规则布局参数（rowStart 属于内置布局键，旧逻辑每次启动都会改回去）
    rule = next(
        candidate
        for code in EXCEL_FIELD_PATHS
        for candidate in database.list_system_field_rules(code)
        if candidate["sourceType"] == "EXCEL" and "rowStart" in candidate["config"]
    )
    database.save_system_field_rule({**rule, "config": {**rule["config"], "rowStart": 4}}, rule["id"])
    # 管理员修改二：遗留映射的 source_path
    with database.connect() as connection:
        connection.execute(
            "UPDATE admin_mapping_rules SET source_path='$.custom.adminOverride' WHERE field_code='samples[].field3'"
        )
        connection.execute(
            "UPDATE lims_field_catalog SET cardinality='ONE' WHERE field_code=?", (rule["fieldCode"],)
        )

    # 模拟第二次启动
    repository.seed()
    ensure_excel_field_rules(database)

    refreshed = next(r for r in database.list_system_field_rules(rule["fieldCode"]) if r["id"] == rule["id"])
    assert refreshed["config"]["rowStart"] == 4
    with database.connect() as connection:
        path = connection.execute(
            "SELECT source_path FROM admin_mapping_rules WHERE field_code='samples[].field3'"
        ).fetchone()[0]
        cardinality = connection.execute(
            "SELECT cardinality FROM lims_field_catalog WHERE field_code=?", (rule["fieldCode"],)
        ).fetchone()[0]
    assert path == "$.custom.adminOverride"
    assert cardinality == "ONE"


def test_startup_seed_still_heals_legacy_state_on_first_run(tmp_path: Path) -> None:
    """首次启动仍然要完成遗留修正：缺 contextVariables 的 AI 规则会被补全。"""
    database = Database(tmp_path / "seed.db")
    database.initialize()
    repository = RuleAdminRepository(database, PROJECT_ROOT / "mapping" / "template-mapping.json")
    repository.seed()
    field_code = _field_code(database, "narrative.chapter")
    rules = [rule for rule in database.list_system_field_rules(field_code) if rule["sourceType"] == "AI"]
    assert rules, "首次播种应生成 AI 概述规则"
    assert rules[0]["config"]["contextVariables"], "AI 规则必须带上下文变量"
