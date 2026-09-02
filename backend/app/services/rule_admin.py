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
    seed_physical_table_index, DEFAULT_TEMPLATE_CHAPTERS, SOLUTION_VIEW_COLLECTIONS,
    STANDARD_FIELD_GROUP_NAMES, STRUCTURED_UNIT_COLLECTIONS,
)
from .lims_parser_profiles import HTML_TABLE_LEGACY_DEFAULTS, HTML_TABLE_PARSER_PROFILES
from .lims_catalog_defaults import ensure_lims_catalog_defaults
from .system_field_defaults import ensure_system_field_defaults
from .system_field_groups import ensure_system_field_groups

# 一次性遗留映射迁移标记：完成后管理员对映射/表格规则/数据源配置的修改不再被启动回滚
LEGACY_RULES_MIGRATION = "2026_admin_legacy_rules_migration_v1"


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


def _standard_code_from_path(path: str) -> str:
    return path.removeprefix("$.").replace("[*]", "").strip(".")


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
        self._migrate_legacy_rules()
        self._assign_unmapped_chapters()
        self._seed_lims_field_catalog()
        ensure_system_field_defaults(self.database)
        ensure_system_field_groups(self.database)
        ensure_lims_catalog_defaults(self.database)
        self._localize_standard_field_groups()
        self._annotate_lims_rules()
        self._seed_template_catalog()
        self.save_active_workspace()

    def _seed_lims_field_catalog(self) -> None:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT source_path,word_label,data_type FROM admin_mapping_rules
                   WHERE source_type='LIMS' AND source_path<>'' ORDER BY id"""
            ).fetchall()]
        seen: set[str] = set()
        scalar_columns = {
            "project.id": "project_id", "project.name": "project_name",
            "document.code": "document_code", "document.version": "document_version",
        }
        for row in rows:
            code = _standard_code_from_path(row["source_path"])
            if not code or code in seen:
                continue
            seen.add(code)
            parts = code.split(".", 1)
            collection = parts[0]
            json_key = parts[1] if len(parts) > 1 else ""
            scalar_column = scalar_columns.get(code)
            if self.database.get_lims_field(code):
                continue
            self.database.upsert_lims_field({
                "fieldCode": code, "label": row["word_label"] or code,
                "groupCode": STANDARD_FIELD_GROUP_NAMES.get(collection, collection),
                "collectionCode": collection, "dataType": row["data_type"],
                "cardinality": "MANY" if "[*]" in row["source_path"] else "ONE",
                "dbTable": "lims_experiments" if scalar_column else "lims_standard_records",
                "dbColumn": scalar_column or "data_json", "jsonKey": "" if scalar_column else json_key,
                "legacyJsonPath": row["source_path"], "enabled": True,
            })
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE admin_mapping_rules SET standard_field_code=replace(replace(source_path,'$.',''),'[*]','')
                   WHERE source_type='LIMS' AND source_path<>'' AND standard_field_code=''"""
            )
        for field in self.database.list_lims_fields(True):
            rules = self.database.list_system_field_rules(field["fieldCode"])
            if field.get("legacyJsonPath") and not rules:
                self.database.save_system_field_rule({
                    "fieldCode": field["fieldCode"], "name": "已有标准数据路径",
                    "sourceType": "LIMS", "transform": "TRIM", "priority": 100,
                    "config": {"extractionType": "NORMALIZED_PATH",
                               "sourcePath": field["legacyJsonPath"]}, "enabled": True,
                })

    def _localize_standard_field_groups(self) -> None:
        """Translate known display groups without changing data collection codes."""
        with self.database.connect() as connection:
            for group_code, group_name in STANDARD_FIELD_GROUP_NAMES.items():
                connection.execute(
                    "UPDATE lims_field_catalog SET group_code=%s,updated_at=%s WHERE group_code=%s",
                    (group_name, now_iso(), group_code),
                )

    def _annotate_lims_rules(self) -> None:
        """Persist deterministic upstream parser details in generated field rules."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT r.id,r.field_code,r.name,r.config,
                          f.collection_code,f.json_key,f.db_table,f.db_column
                   FROM system_field_rules r
                   JOIN lims_field_catalog f ON f.field_code=r.field_code
                   WHERE r.source_type='LIMS'"""
            ).fetchall()
            for row in rows:
                collection = str(row["collection_code"] or "")
                config = json.loads(row["config"] or "{}")
                section_pattern = str(config.get("sectionPattern") or "")
                header_pattern = str(config.get("headerPattern") or "")
                name = str(row["name"] or "")
                if collection in HTML_TABLE_PARSER_PROFILES:
                    profile, default_section, default_header = HTML_TABLE_PARSER_PROFILES[collection]
                    generated = {
                        "parser": "HTML_TABLE_GRID", "parserProfile": profile,
                        "inputField": "UNITBODY", "unitType": "RichText", "tableSelector": "table",
                        "outputCollection": collection, "outputField": row["json_key"] or "",
                        "preserveEvidence": True,
                    }
                    legacy_defaults = HTML_TABLE_LEGACY_DEFAULTS.get(collection, ("", ""))
                    if not section_pattern or section_pattern == legacy_defaults[0]:
                        section_pattern = default_section
                    if not header_pattern or header_pattern == legacy_defaults[1]:
                        header_pattern = default_header
                    if name in {"已有标准数据路径", "Existing normalized path"}:
                        name = "HTML 表格解析 → 标准字段"
                elif collection in SOLUTION_VIEW_COLLECTIONS:
                    generated = {
                        "parser": "HTML_TABLE_GRID", "parserProfile": "SOLUTION_PREPARATION_TABLE",
                        "inputField": "UNITBODY", "unitType": "RichText", "tableSelector": "table",
                        "outputCollection": collection, "outputField": row["json_key"] or "",
                        "derivedFromCollection": "solutions", "preserveEvidence": True,
                    }
                    section_pattern = section_pattern or r"实验设计|溶液配制"
                    header_pattern = header_pattern or r"溶液名称|名称.*配制方法|溶液配制"
                    if name in {"已有标准数据路径", "Existing normalized path"}:
                        name = "溶液表格解析 → 标准字段"
                elif collection in STRUCTURED_UNIT_COLLECTIONS:
                    generated = {
                        "parser": "STRUCTURED_UNIT", "parserProfile": collection.upper(),
                        "inputField": "UNITBODY", "unitType": "Structured",
                        "outputCollection": collection, "outputField": row["json_key"] or "",
                        "preserveEvidence": True,
                    }
                    if name in {"已有标准数据路径", "Existing normalized path"}:
                        name = "结构化 UNITBODY → 标准字段"
                elif row["db_table"] == "lims_experiments":
                    generated = {
                        "parser": "INSTANCE_FIELD", "inputField": row["db_column"],
                        "outputCollection": collection, "outputField": row["json_key"] or "",
                    }
                else:
                    generated = {
                        "parser": "NORMALIZED_JSON", "inputField": "UNITBODY",
                        "outputCollection": collection, "outputField": row["json_key"] or "",
                        "preserveEvidence": True,
                    }
                for key, value in generated.items():
                    config.setdefault(key, value)
                config.update({"sectionPattern": section_pattern, "headerPattern": header_pattern})
                connection.execute(
                    "UPDATE system_field_rules SET name=%s,config=%s,updated_at=%s WHERE id=%s",
                    (name, json.dumps(config, ensure_ascii=False), now_iso(), row["id"]),
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

    def _seed_content_blocks(self) -> None:
        """Turn the legacy inferred mapping groups into persistent, editable blocks."""
        with self.database.connect() as connection:
            if connection.execute("SELECT COUNT(*) FROM admin_content_blocks").fetchone()[0]:
                return
            rows = [dict(row) for row in connection.execute(
                """SELECT m.*,mc.chapter_id FROM admin_mapping_rules m
                   JOIN admin_mapping_chapters mc ON mc.mapping_id=m.id ORDER BY m.id"""
            ).fetchall()]
            table_modes = {row["table_no"]: row["mode"] for row in connection.execute(
                "SELECT table_no,mode FROM admin_table_rules"
            ).fetchall()}
            groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
            for item in rows:
                key = item.get("table_no") or item.get("location_id") or str(item["id"])
                if key in {"TEXT", "COVER", "HEADER"} and item.get("repeat_type") in {"", "NONE"}:
                    key = item.get("field_code") or key
                groups[(int(item["chapter_id"]), str(key))].append(item)
            for order_no, ((chapter_id, _), items) in enumerate(groups.items()):
                first = items[0]
                table_no = str(first.get("table_no") or "")
                sources = {str(item.get("source_type") or "") for item in items}
                if sources == {"FIXED"}:
                    kind = "FIXED"
                elif table_modes.get(table_no) == "MATRIX":
                    kind = "MATRIX"
                elif re.fullmatch(r"T\d+", table_no) or any(item.get("repeat_type") not in {"", "NONE"} for item in items):
                    kind = "REPEATING_TABLE"
                elif "AI" in sources:
                    kind = "AI_NARRATIVE"
                elif "CALCULATED" in sources:
                    kind = "CALCULATED"
                else:
                    kind = "MAPPED_FIELD"
                is_table = bool(re.fullmatch(r"T\d+", table_no))
                title = str(first.get("word_label") or "字段组") + ("表格" if is_table else "")
                source_match = re.match(r"(\$\.[A-Za-z0-9_]+\[\*\])", str(first.get("source_path") or ""))
                source_path = source_match.group(1) if source_match else ""
                cursor = connection.execute(
                    """INSERT INTO admin_content_blocks(chapter_id,title,kind,table_no,source_path,repeat_key,
                       prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,updated_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (chapter_id, title, kind, table_no if is_table else "", source_path,
                     first.get("repeat_key") or "", f"body.{table_no}.dataRow" if is_table else "",
                     "", "", "KEEP", "NONE", order_no, 1, now_iso()),
                )
                connection.executemany(
                    "INSERT INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(%s,%s,%s)",
                    [(item["id"], cursor.lastrowid, order_no) for order_no, item in enumerate(items)],
                )

    def _migrate_content_block_rules(self) -> None:
        with self.database.connect() as connection:
            block_rows = connection.execute(
                """SELECT b.id,b.title,b.table_no,m.source_type,m.repeat_type,tr.mode
                   FROM admin_content_blocks b
                   LEFT JOIN admin_mapping_blocks mb ON mb.block_id=b.id
                   LEFT JOIN admin_mapping_rules m ON m.id=mb.mapping_id
                   LEFT JOIN admin_table_rules tr ON tr.table_no=b.table_no
                   ORDER BY b.id,m.id"""
            ).fetchall()
            grouped: dict[int, list[Any]] = defaultdict(list)
            for row in block_rows:
                grouped[int(row["id"])].append(row)
            for block_id, items in grouped.items():
                table_no = str(items[0]["table_no"] or "")
                is_table = bool(re.fullmatch(r"T\d+", table_no))
                sources = {str(item["source_type"] or "") for item in items if item["source_type"]}
                repeats = {str(item["repeat_type"] or "") for item in items if item["repeat_type"]}
                mode = str(items[0]["mode"] or "")
                if sources == {"FIXED"}:
                    kind = "FIXED"
                elif mode == "MATRIX":
                    kind = "MATRIX"
                elif is_table or any(value not in {"", "NONE"} for value in repeats):
                    kind = "REPEATING_TABLE"
                elif "AI" in sources:
                    kind = "AI_NARRATIVE"
                elif "CALCULATED" in sources:
                    kind = "CALCULATED"
                else:
                    kind = "MAPPED_FIELD"
                title = str(items[0]["title"])
                if not is_table and title.endswith("表格"):
                    title = title[:-2]
                connection.execute(
                    "UPDATE admin_content_blocks SET title=%s,kind=%s,table_no=%s,updated_at=%s WHERE id=%s",
                    (title, kind, table_no if is_table else "", now_iso(), block_id),
                )
            connection.execute(
                """UPDATE admin_content_blocks SET title=substr(title,1,length(title)-2),updated_at=%s
                   WHERE kind NOT IN ('REPEATING_TABLE','MATRIX') AND table_no NOT REGEXP '^T[0-9]'
                   AND title LIKE '%表格'""",
                (now_iso(),),
            )
            rows = connection.execute(
                """SELECT b.id,b.table_no,m.source_path,m.repeat_key FROM admin_content_blocks b
                   JOIN admin_mapping_blocks mb ON mb.block_id=b.id
                   JOIN admin_mapping_rules m ON m.id=mb.mapping_id
                   WHERE b.source_path='' ORDER BY b.id,m.id"""
            ).fetchall()
            handled: set[int] = set()
            for row in rows:
                block_id = int(row["id"])
                if block_id in handled:
                    continue
                handled.add(block_id)
                source_match = re.match(r"(\$\.[A-Za-z0-9_]+\[\*\])", str(row["source_path"] or ""))
                connection.execute(
                    """UPDATE admin_content_blocks SET source_path=%s,repeat_key=%s,prototype_location=%s,updated_at=%s
                       WHERE id=%s""",
                    (source_match.group(1) if source_match else "", row["repeat_key"] or "",
                     f"body.{row['table_no']}.dataRow" if re.fullmatch(r"T\d+", str(row["table_no"])) else "",
                     now_iso(), block_id),
                )

    def _migrate_legacy_rules(self) -> None:
        """One-time legacy migration; admin changes must not be rolled back on later startups."""
        if self.database.migration_applied(LEGACY_RULES_MIGRATION):
            return
        self._apply_legacy_rules_migration()
        # 失败时不标记，下次启动重试
        self.database.mark_migration_applied(LEGACY_RULES_MIGRATION)

    def _apply_legacy_rules_migration(self) -> None:
        """Correct locations that the original prototype generated from column labels only."""
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE admin_mapping_rules SET repeat_type='NONE', source_path='$.lodConclusion',
                   updated_at=%s WHERE control_tag='lod.conclusion'""", (now_iso(),)
            )
            solution_sources = {
                "T12": "systemSuitabilitySolutions", "T14": "specificitySolutions",
                "T21": "repeatabilitySolutions", "T23": "intermediatePrecisionSolutions",
                "T27": "accuracySolutions", "T30": "stabilitySolutions", "T32": "robustnessSolutions",
            }
            for table_no, collection in solution_sources.items():
                connection.execute(
                    """UPDATE admin_mapping_rules SET source_path=replace(source_path,'$.solutions[*]',%s),
                       source_pending=0, updated_at=%s WHERE table_no=%s""",
                    (f"$.{collection}[*]", now_iso(), table_no),
                )
            connection.execute(
                """UPDATE admin_mapping_rules SET source_path=replace(source_path,'$.linearity[*]',
                   '$.intermediateLinearity[*]'), source_pending=0, updated_at=%s WHERE table_no='T25'""",
                (now_iso(),),
            )
            connection.execute(
                """UPDATE admin_mapping_rules SET enabled=0, source_pending=1, updated_at=%s
                   WHERE table_no IN ('T24','T37')""", (now_iso(),)
            )
            connection.execute(
                """UPDATE admin_table_rules SET enabled=0,
                   notes='当前 Word 模板没有该独立表格；数据保留在 LIMS 标准模型和来源证据中', updated_at=%s
                   WHERE table_no IN ('T24','T37')""", (now_iso(),)
            )
            connected_collections = (
                "impurity", "limit", "validationSummary", "methodParameters", "systemSuitability",
                "specificity", "lod", "loq", "linearityPreparation", "linearity", "repeatability",
                "intermediatePrecision", "blankAmount", "accuracy", "solutionStability",
                "robustnessSpecificity", "robustnessSequence", "robustnessResult", "sampleResults",
            )
            conditions = " OR ".join("source_path LIKE %s" for _ in connected_collections)
            connection.execute(
                f"UPDATE admin_mapping_rules SET source_pending=0, updated_at=%s WHERE enabled=1 AND ({conditions})",
                (now_iso(), *(f"$.{name}[*]%" for name in connected_collections)),
            )
            connection.execute(
                """UPDATE admin_mapping_rules SET location_id='body.T17.row3.cell2', field_code='lod.conclusion',
                   source_path='$.lodConclusion', repeat_type='NONE', repeat_key='', control_tag='lod.conclusion',
                   updated_at=%s WHERE location_id='body.T17.dataRow.cell8'""", (now_iso(),)
            )
            direct_lims_prefixes = (
                "project.name", "document.code", "document.version", "approval[]",
                "samples[]", "referenceStandards[]", "instruments[]", "columns[]", "reagents[]",
            )
            conditions = " OR ".join("field_code LIKE %s" for _ in direct_lims_prefixes)
            connection.execute(
                f"UPDATE admin_mapping_rules SET source_pending=0, updated_at=%s WHERE source_type='LIMS' AND ({conditions})",
                (now_iso(), *(f"{prefix}%" for prefix in direct_lims_prefixes)),
            )
            normalized_paths = {
                "samples[].field3": "$.samples[*].specification",
                "samples[].field4": "$.samples[*].clientName",
                "samples[].field5": "$.samples[*].remark",
                "columns[].field1": "$.columns[*].name",
                "columns[].field2": "$.columns[*].specification",
                "columns[].field5": "$.columns[*].stationaryPhase",
                "reagents[].field2": "$.reagents[*].grade",
            }
            for field_code, source_path in normalized_paths.items():
                connection.execute(
                    "UPDATE admin_mapping_rules SET source_path=%s, source_pending=0, updated_at=%s WHERE field_code=%s",
                    (source_path, now_iso(), field_code),
                )
            row = connection.execute("SELECT config FROM admin_data_sources WHERE code='lims-primary'").fetchone()
            if row:
                config = json.loads(row["config"])
                if config.get("connector") == "mock":
                    config.update({"connector": "sql", "previewAdapter": "oracle", "instanceKey": "INSTANCEID",
                                   "unitBodyField": "UNITBODY", "query": ""})
                    connection.execute("UPDATE admin_data_sources SET config=%s, updated_at=%s WHERE code='lims-primary'",
                                       (json.dumps(config, ensure_ascii=False), now_iso()))
                if config.get("connector") == "sql":
                    config["previewAdapter"] = "oracle"
                config.setdefault("recognitionRules", {
                    "sectionPaths": ["实验设计", "实验过程", "仪器方法", "实验结果", "实验结论"],
                    "classifier": "section-path-and-header-signature",
                    "deduplication": "semantic-whitespace-normalized",
                    "conflictPolicy": "require-user-selection",
                    "preserveUnmatchedEvidence": True,
                })
                connection.execute("UPDATE admin_data_sources SET config=%s, updated_at=%s WHERE code='lims-primary'",
                                   (json.dumps(config, ensure_ascii=False), now_iso()))
            title_mapping = connection.execute(
                "SELECT 1 FROM admin_mapping_rules WHERE field_code='project.name.body'"
            ).fetchone()
            if not title_mapping:
                connection.execute(
                    """INSERT INTO admin_mapping_rules(location_id,section_code,table_no,word_label,field_code,
                       data_type,source_type,source_path,repeat_type,repeat_key,merge_rule,fill_rule,
                       calculation_rule,control_tag,required,source_pending,enabled,updated_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    ("body.paragraph4", "cover", "COVER", "封面项目名称", "project.name.body", "string",
                     "LIMS", "$.project.name", "NONE", "", "PRESERVE", "TEXT", "",
                     "project.name.body", 1, 0, 1, now_iso()),
                )
            dynamic_paragraphs = (
                (47, "概述正文", "narrative.overview", "AI"),
                (49, "目的正文", "narrative.purpose", "AI"),
                (81, "验证总结", "narrative.validationConclusion", "AI"),
                (121, "定量限结果表标题", "caption.loq", "LIMS"),
                (134, "线性结果表标题", "caption.linearity", "LIMS"),
                (145, "重复性结果表标题", "caption.repeatability", "LIMS"),
                (157, "中间精密度线性表标题", "caption.intermediateLinearity", "LIMS"),
                (159, "中间精密度加标表标题", "caption.intermediateSpiked", "LIMS"),
                (172, "准确度结果表标题", "caption.accuracy", "LIMS"),
                (183, "稳定性结果表标题", "caption.stability", "LIMS"),
                (195, "耐用性结果表标题", "caption.robustness", "LIMS"),
                (236, "附件图谱名称", "attachment.chromatogramTitle", "LIMS"),
            )
            for paragraph_no, label, field_code, source_type in dynamic_paragraphs:
                exists = connection.execute(
                    "SELECT 1 FROM admin_mapping_rules WHERE field_code=%s", (field_code,)
                ).fetchone()
                if exists:
                    continue
                connection.execute(
                    """INSERT INTO admin_mapping_rules(location_id,section_code,table_no,word_label,field_code,
                       data_type,source_type,source_path,repeat_type,repeat_key,merge_rule,fill_rule,
                       calculation_rule,control_tag,required,source_pending,enabled,updated_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (f"body.paragraph{paragraph_no}", "narrative", "TEXT", label, field_code, "richText",
                     source_type, "", "NONE", "", "PRESERVE", "TEXT", "", field_code,
                     0, 1, 1, now_iso()),
                )

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
