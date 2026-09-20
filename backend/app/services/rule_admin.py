import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..database import Database, now_iso
from .template_catalog_repository import TemplateCatalogRepositoryMixin
from .content_block_repository import ContentBlockRepositoryMixin
from .mapping_validation_repository import MappingValidationRepositoryMixin
from .mapping_repository import MappingRepositoryMixin
from .chapter_repository import ChapterRepositoryMixin
from .designer_config_repository import DesignerConfigRepositoryMixin
from .workspace_repository import WorkspaceRepositoryMixin
from .template_block_repository import TemplateBlockRepositoryMixin
from .runtime_version_repository import RuntimeVersionRepositoryMixin
from .rule_admin_defaults import (
    SEED_CLEAR_OBJECT_TABLES, SEED_MATRIX_LAYOUT, SEED_MATRIX_TABLES, SEED_PRESERVED_ROW_LABELS,
    seed_physical_table_index, DEFAULT_TEMPLATE_CHAPTERS,
    STANDARD_FIELD_GROUP_NAMES,
)
from .lims_catalog_defaults import ensure_lims_catalog_defaults
from .lims_direct_rule_migration import migrate_lims_direct_rules
from .system_field_defaults import ensure_system_field_defaults
from .system_field_groups import ensure_system_field_groups
from .excel_rule_defaults import ensure_excel_field_rules
from .system_field_rule_invariant import ensure_single_system_field_rule_schema


def _chapter_for_mapping(item: dict[str, Any]) -> str:
    field = str(item.get("fieldCode", ""))
    section = str(item.get("sectionCode", ""))
    if field == "narrative.overview": return "1"
    if field == "narrative.purpose": return "2"
    if field == "narrative.validationConclusion": return "5.2"
    if section == "header": return "headerFooter"
    if section in {"approval", "cover"}: return "cover"
    if section == "toc": return "3"
    if section == "3.2.limit": return "3.2"
    if section == "3.3.impurity": return "3.3"
    if section == "4.1.samples": return "4.1"
    if section == "4.2.referenceStandards": return "4.2"
    if section == "4.3.instruments": return "4.3"
    if section == "4.3.columns": return "4.4"
    if section == "4.5.reagents": return "4.5"
    if section == "5.validationSummary": return "5.1"
    if section == "6.methodParameters": return "6"
    if section.startswith("7."): return section[:3]
    if section == "8.sampleResults": return "8.4"
    if section == "versionHistory": return "12"
    if section == "attachment": return "11"
    return "cover"


class RuleAdminRepository(
    RuntimeVersionRepositoryMixin, WorkspaceRepositoryMixin,
    DesignerConfigRepositoryMixin, ChapterRepositoryMixin,
    MappingRepositoryMixin, MappingValidationRepositoryMixin,
    ContentBlockRepositoryMixin, TemplateCatalogRepositoryMixin, TemplateBlockRepositoryMixin,
):
    def __init__(self, database: Database, mapping_path: Path):
        self.database = database
        self.mapping_path = mapping_path

    def seed(self) -> None:
        ensure_single_system_field_rule_schema(self.database)
        self._seed_template_chapters()
        with self.database.connect() as connection:
            mapping_count = connection.execute("SELECT COUNT(*) FROM admin_mapping_rules").fetchone()[0]
        if mapping_count == 0:
            payload = json.loads(self.mapping_path.read_text(encoding="utf-8-sig"))
            for item in payload["mappings"]:
                self.create_mapping(item)
            self._seed_table_rules(payload["mappings"])
        with self.database.connect() as connection:
            source_count = connection.execute("SELECT COUNT(*) FROM admin_data_sources").fetchone()[0]
        if source_count == 0:
            defaults = [
                ("lims-primary", "生产 LIMS", "LIMS", 10,
                 {"connector": "sql", "previewAdapter": "oracle", "instanceKey": "INSTANCEID",
                  "unitBodyField": "UNITBODY", "query": ""}),
                ("pdf-extractor", "PDF 提取", "PDF", 20, {"engine": "PyMuPDF", "ocrEnabled": False}),
                ("manual-entry", "人工录入", "MANUAL", 90, {"requiresReason": True}),
                ("ai-draft", "AI 叙述草稿", "AI", 80, {"provider": "unconfigured", "requireApproval": True}),
            ]
            for code, name, source_type, priority, config in defaults:
                self.upsert_data_source({"code": code, "name": name, "sourceType": source_type,
                                         "priority": priority, "enabled": True, "config": config})
        self._assign_unmapped_chapters()
        ensure_system_field_defaults(self.database)
        ensure_system_field_groups(self.database)
        ensure_lims_catalog_defaults(self.database)
        ensure_excel_field_rules(self.database)
        self._localize_standard_field_groups()
        migrate_lims_direct_rules(self.database)
        self._seed_template_catalog()
        self.save_active_workspace()

    def _localize_standard_field_groups(self) -> None:
        """Translate known display groups without changing data collection codes."""
        with self.database.connect() as connection:
            for group_code, group_name in STANDARD_FIELD_GROUP_NAMES.items():
                connection.execute(
                    "UPDATE lims_field_catalog SET group_code=%s,updated_at=%s WHERE group_code=%s",
                    (group_name, now_iso(), group_code),
                )

    def _seed_template_catalog(self) -> None:
        with self.database.connect() as connection:
            if connection.execute("SELECT COUNT(*) FROM admin_templates").fetchone()[0]:
                return
        timestamp = now_iso()
        template_id = "default-report-template"
        version_id = "default-report-template-v1"
        snapshot = self.snapshot()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO admin_templates(id,code,name,description,status,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (template_id, "REPORT", "默认报告模板", "由现有报告模板和映射规则自动迁移", "ACTIVE", timestamp, timestamp),
            )
            connection.execute(
                """INSERT INTO admin_template_versions(id,template_id,version_no,status,note,snapshot,
                   validation_report,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (version_id, template_id, 1, "DRAFT", "迁移现有模板配置",
                 json.dumps(snapshot, ensure_ascii=False), "{}", timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO admin_template_workspace(id,active_template_id,active_version_id,updated_at) VALUES(1,%s,%s,%s) ON DUPLICATE KEY UPDATE active_template_id=VALUES(active_template_id),active_version_id=VALUES(active_version_id),updated_at=VALUES(updated_at)",
                (template_id, version_id, timestamp),
            )

    def _seed_template_chapters(self) -> None:
        with self.database.connect() as connection:
            exists = connection.execute("SELECT COUNT(*) FROM admin_template_chapters").fetchone()[0]
            if exists:
                return
            ids: dict[str, int] = {}
            for parent_code, code, title, page_hint, order_no in DEFAULT_TEMPLATE_CHAPTERS:
                parent_id = ids.get(parent_code) if parent_code else None
                cursor = connection.execute(
                    "INSERT INTO admin_template_chapters(parent_id,code,title,page_hint,order_no,enabled,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (parent_id, code, title, page_hint, order_no, 1, now_iso()),
                )
                ids[code] = cursor.lastrowid

    def _assign_unmapped_chapters(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT m.id,m.field_code,m.section_code,m.source_type FROM admin_mapping_rules m "
                "LEFT JOIN admin_mapping_chapters mc ON mc.mapping_id=m.id WHERE mc.mapping_id IS NULL"
            ).fetchall()
            for row in rows:
                chapter_code = _chapter_for_mapping({"fieldCode": row["field_code"], "sectionCode": row["section_code"], "sourceType": row["source_type"]})
                chapter = connection.execute("SELECT id FROM admin_template_chapters WHERE code=%s", (chapter_code,)).fetchone()
                if chapter:
                    connection.execute("INSERT IGNORE INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(%s,%s)", (row["id"], chapter["id"]))

    def _seed_table_rules(self, mappings: list[dict[str, Any]]) -> None:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in mappings:
            if item["tableNo"].startswith("T"):
                groups[item["tableNo"]].append(item)
        matrix_tables = {"T11", "T20", "T24", "T25"}
        multi_header = {"T13": 2, "T31": 2}
        for table_no, entries in groups.items():
            # 布局字段一并写入，保证新装环境里的表格规则在设计器中就是完整可见的
            self.upsert_table_rule({
                "tableNo": table_no,
                "sectionCode": entries[0]["sectionCode"],
                "mode": "STATIC" if table_no == "T2" else ("MATRIX" if table_no in matrix_tables else "ROW_REPEAT"),
                "headerRows": multi_header.get(table_no, 1),
                "dataRowStart": multi_header.get(table_no, 1) + 1,
                "dataRowEnd": multi_header.get(table_no, 1) + 1,
                "footerRows": 0,
                "recordKey": entries[0].get("repeatKey", ""),
                "mergeFields": [item["fieldCode"] for item in entries if item.get("mergeRule") == "VERTICAL_BY_VALUE"],
                "physicalTableIndex": seed_physical_table_index(table_no),
                "preservedRowLabels": list(SEED_PRESERVED_ROW_LABELS),
                "clearEmbeddedObjects": table_no in SEED_CLEAR_OBJECT_TABLES,
                "matrixLayout": (SEED_MATRIX_LAYOUT if table_no in SEED_MATRIX_TABLES else ""),
                "enabled": table_no != "T2",
                "notes": "由原映射自动生成，发布前需在模板预览中确认数据行范围",
            })
