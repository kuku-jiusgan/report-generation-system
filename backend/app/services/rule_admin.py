import json
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..database import Database, now_iso
from .calculation_engine import validate_calculation


MAPPING_COLUMNS = {
    "locationId": "location_id",
    "sectionCode": "section_code",
    "tableNo": "table_no",
    "wordLabel": "word_label",
    "fieldCode": "field_code",
    "dataType": "data_type",
    "sourceType": "source_type",
    "sourcePath": "source_path",
    "standardFieldCode": "standard_field_code",
    "repeatType": "repeat_type",
    "repeatKey": "repeat_key",
    "mergeRule": "merge_rule",
    "fillRule": "fill_rule",
    "calculationRule": "calculation_rule",
    "calculationExpression": "calculation_expression",
    "calculationDependencies": "calculation_dependencies",
    "calculationScope": "calculation_scope",
    "calculationPrecision": "calculation_precision",
    "calculationNullBehavior": "calculation_null_behavior",
    "controlTag": "control_tag",
    "required": "required",
    "sourcePending": "source_pending",
    "enabled": "enabled",
}
REVERSE_MAPPING_COLUMNS = {value: key for key, value in MAPPING_COLUMNS.items()}

DEFAULT_TEMPLATE_CHAPTERS = [
    ("", "cover", "封面", None, 0),
    ("", "headerFooter", "页眉与页脚", None, 1),
    ("", "1", "概述", 4, 2),
    ("", "2", "目的", 4, 3),
    ("", "3", "参考文件、限度标准", 4, 4),
    ("3", "3.1", "参考文件", 4, 5), ("3", "3.2", "限度", 4, 6), ("3", "3.3", "杂质信息", 4, 7),
    ("", "4", "物料及仪器信息", 5, 8),
    ("4", "4.1", "供试品", 5, 9), ("4", "4.2", "对照品", 5, 10), ("4", "4.3", "仪器", 5, 11),
    ("4", "4.4", "色谱柱", 6, 12), ("4", "4.5", "试剂", 6, 13),
    ("", "5", "结果汇总", 6, 14), ("5", "5.1", "验证结果汇总", 6, 15), ("5", "5.2", "验证结论", 7, 16),
    ("", "6", "分析方法", 8, 17), ("", "7", "验证内容", 9, 18),
    ("7", "7.1", "系统适用性", 9, 19), ("7", "7.2", "专属性", 10, 20),
    ("7", "7.3", "检测限与定量限", 11, 21), ("7", "7.4", "线性与范围", 12, 22),
    ("7", "7.5", "重复性", 14, 23), ("7", "7.6", "中间精密度", 15, 24),
    ("7", "7.7", "准确度", 18, 25), ("7", "7.8", "溶液稳定性", 20, 26), ("7", "7.9", "耐用性", 21, 27),
    ("", "8", "供试品检测", 22, 28), ("8", "8.1", "溶液配制", 22, 29), ("8", "8.2", "试验过程", 22, 30),
    ("8", "8.3", "可接受标准", 22, 31), ("8", "8.4", "结果及结论", 23, 32), ("8", "8.5", "相关图谱", 23, 33),
    ("", "9", "计算公式", 23, 34), ("", "10", "偏差", 24, 35), ("", "11", "附件", 24, 36),
    ("", "12", "变更历史", 25, 37),
]


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


class RuleAdminRepository:
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
                 {"connector": "sql", "previewAdapter": "xlsx", "instanceKey": "INSTANCEID",
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
        self._seed_content_blocks()
        self._migrate_content_block_rules()
        self._seed_lims_field_catalog()
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
                "fieldCode": code, "label": row["word_label"] or code, "groupCode": collection,
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
            if field.get("legacyJsonPath") and not self.database.list_lims_extraction_rules(field["fieldCode"]):
                self.database.save_lims_extraction_rule({
                    "fieldCode": field["fieldCode"], "name": "已有标准数据路径",
                    "sourceType": "NORMALIZED_PATH", "sourcePath": field["legacyJsonPath"],
                    "transform": "TRIM", "priority": 100, "config": {}, "enabled": True,
                })

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
                "INSERT INTO admin_templates(id,code,name,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (template_id, "REPORT", "默认报告模板", "由现有报告模板和映射规则自动迁移", "ACTIVE", timestamp, timestamp),
            )
            connection.execute(
                """INSERT INTO admin_template_versions(id,template_id,version_no,status,note,snapshot,
                   validation_report,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (version_id, template_id, 1, "DRAFT", "迁移现有模板配置",
                 json.dumps(snapshot, ensure_ascii=False), "{}", timestamp, timestamp),
            )
            connection.execute(
                "INSERT OR REPLACE INTO admin_template_workspace(id,active_template_id,active_version_id,updated_at) VALUES(1,?,?,?)",
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
                    "INSERT INTO admin_template_chapters(parent_id,code,title,page_hint,order_no,enabled,updated_at) VALUES(?,?,?,?,?,?,?)",
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
                chapter = connection.execute("SELECT id FROM admin_template_chapters WHERE code=?", (chapter_code,)).fetchone()
                if chapter:
                    connection.execute("INSERT OR IGNORE INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(?,?)", (row["id"], chapter["id"]))

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
                       prototype_location,order_no,enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (chapter_id, title, kind, table_no if is_table else "", source_path,
                     first.get("repeat_key") or "", f"body.{table_no}.dataRow" if is_table else "",
                     order_no, 1, now_iso()),
                )
                connection.executemany(
                    "INSERT INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(?,?,?)",
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
                    "UPDATE admin_content_blocks SET title=?,kind=?,table_no=?,updated_at=? WHERE id=?",
                    (title, kind, table_no if is_table else "", now_iso(), block_id),
                )
            connection.execute(
                """UPDATE admin_content_blocks SET title=substr(title,1,length(title)-2),updated_at=?
                   WHERE kind NOT IN ('REPEATING_TABLE','MATRIX') AND table_no NOT GLOB 'T[0-9]*'
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
                    """UPDATE admin_content_blocks SET source_path=?,repeat_key=?,prototype_location=?,updated_at=?
                       WHERE id=?""",
                    (source_match.group(1) if source_match else "", row["repeat_key"] or "",
                     f"body.{row['table_no']}.dataRow" if re.fullmatch(r"T\d+", str(row["table_no"])) else "",
                     now_iso(), block_id),
                )

    def _migrate_legacy_rules(self) -> None:
        """Correct locations that the original prototype generated from column labels only."""
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE admin_mapping_rules SET repeat_type='NONE', source_path='$.lodConclusion',
                   updated_at=? WHERE control_tag='lod.conclusion'""", (now_iso(),)
            )
            solution_sources = {
                "T12": "systemSuitabilitySolutions", "T14": "specificitySolutions",
                "T21": "repeatabilitySolutions", "T23": "intermediatePrecisionSolutions",
                "T27": "accuracySolutions", "T30": "stabilitySolutions", "T32": "robustnessSolutions",
            }
            for table_no, collection in solution_sources.items():
                connection.execute(
                    """UPDATE admin_mapping_rules SET source_path=replace(source_path,'$.solutions[*]',?),
                       source_pending=0, updated_at=? WHERE table_no=?""",
                    (f"$.{collection}[*]", now_iso(), table_no),
                )
            connection.execute(
                """UPDATE admin_mapping_rules SET source_path=replace(source_path,'$.linearity[*]',
                   '$.intermediateLinearity[*]'), source_pending=0, updated_at=? WHERE table_no='T25'""",
                (now_iso(),),
            )
            connection.execute(
                """UPDATE admin_mapping_rules SET enabled=0, source_pending=1, updated_at=?
                   WHERE table_no IN ('T24','T37')""", (now_iso(),)
            )
            connection.execute(
                """UPDATE admin_table_rules SET enabled=0,
                   notes='当前 Word 模板没有该独立表格；数据保留在 LIMS 标准模型和来源证据中', updated_at=?
                   WHERE table_no IN ('T24','T37')""", (now_iso(),)
            )
            connected_collections = (
                "impurity", "limit", "validationSummary", "methodParameters", "systemSuitability",
                "specificity", "lod", "loq", "linearityPreparation", "linearity", "repeatability",
                "intermediatePrecision", "blankAmount", "accuracy", "solutionStability",
                "robustnessSpecificity", "robustnessSequence", "robustnessResult", "sampleResults",
            )
            conditions = " OR ".join("source_path LIKE ?" for _ in connected_collections)
            connection.execute(
                f"UPDATE admin_mapping_rules SET source_pending=0, updated_at=? WHERE enabled=1 AND ({conditions})",
                (now_iso(), *(f"$.{name}[*]%" for name in connected_collections)),
            )
            connection.execute(
                """UPDATE admin_mapping_rules SET location_id='body.T17.row3.cell2', field_code='lod.conclusion',
                   source_path='$.lodConclusion', repeat_type='NONE', repeat_key='', control_tag='lod.conclusion',
                   updated_at=? WHERE location_id='body.T17.dataRow.cell8'""", (now_iso(),)
            )
            direct_lims_prefixes = (
                "project.name", "document.code", "document.version", "approval[]",
                "samples[]", "referenceStandards[]", "instruments[]", "columns[]", "reagents[]",
            )
            conditions = " OR ".join("field_code LIKE ?" for _ in direct_lims_prefixes)
            connection.execute(
                f"UPDATE admin_mapping_rules SET source_pending=0, updated_at=? WHERE source_type='LIMS' AND ({conditions})",
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
                    "UPDATE admin_mapping_rules SET source_path=?, source_pending=0, updated_at=? WHERE field_code=?",
                    (source_path, now_iso(), field_code),
                )
            row = connection.execute("SELECT config FROM admin_data_sources WHERE code='lims-primary'").fetchone()
            if row:
                config = json.loads(row["config"])
                if config.get("connector") == "mock":
                    config.update({"connector": "sql", "previewAdapter": "xlsx", "instanceKey": "INSTANCEID",
                                   "unitBodyField": "UNITBODY", "query": ""})
                    connection.execute("UPDATE admin_data_sources SET config=?, updated_at=? WHERE code='lims-primary'",
                                       (json.dumps(config, ensure_ascii=False), now_iso()))
                config.setdefault("recognitionRules", {
                    "sectionPaths": ["实验设计", "实验过程", "仪器方法", "实验结果", "实验结论"],
                    "classifier": "section-path-and-header-signature",
                    "deduplication": "semantic-whitespace-normalized",
                    "conflictPolicy": "require-user-selection",
                    "preserveUnmatchedEvidence": True,
                })
                connection.execute("UPDATE admin_data_sources SET config=?, updated_at=? WHERE code='lims-primary'",
                                   (json.dumps(config, ensure_ascii=False), now_iso()))
            title_mapping = connection.execute(
                "SELECT 1 FROM admin_mapping_rules WHERE field_code='project.name.body'"
            ).fetchone()
            if not title_mapping:
                connection.execute(
                    """INSERT INTO admin_mapping_rules(location_id,section_code,table_no,word_label,field_code,
                       data_type,source_type,source_path,repeat_type,repeat_key,merge_rule,fill_rule,
                       calculation_rule,control_tag,required,source_pending,enabled,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    "SELECT 1 FROM admin_mapping_rules WHERE field_code=?", (field_code,)
                ).fetchone()
                if exists:
                    continue
                connection.execute(
                    """INSERT INTO admin_mapping_rules(location_id,section_code,table_no,word_label,field_code,
                       data_type,source_type,source_path,repeat_type,repeat_key,merge_rule,fill_rule,
                       calculation_rule,control_tag,required,source_pending,enabled,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                "enabled": table_no != "T2",
                "notes": "由原映射自动生成，发布前需在模板预览中确认数据行范围",
            })

    @staticmethod
    def _mapping_to_api(row: dict[str, Any]) -> dict[str, Any]:
        item = {REVERSE_MAPPING_COLUMNS.get(key, key): value for key, value in row.items() if key not in {"updated_at"}}
        for key in ("required", "sourcePending", "enabled"):
            if key in item:
                item[key] = bool(item[key])
        item["updatedAt"] = row.get("updated_at")
        dependencies = item.get("calculationDependencies", "[]")
        if isinstance(dependencies, str):
            try:
                item["calculationDependencies"] = json.loads(dependencies)
            except json.JSONDecodeError:
                item["calculationDependencies"] = []
        if "assigned_chapter_id" in row:
            item["chapterId"] = row.get("assigned_chapter_id")
        if "assigned_block_id" in row:
            item["blockId"] = row.get("assigned_block_id")
        return item

    def list_mappings(self, search: str = "", table_no: str = "", source_type: str = "") -> list[dict[str, Any]]:
        clauses, params = [], []
        if search:
            clauses.append("(m.field_code LIKE ? OR m.word_label LIKE ? OR m.location_id LIKE ?)")
            pattern = f"%{search}%"
            params.extend((pattern, pattern, pattern))
        if table_no:
            clauses.append("m.table_no=?")
            params.append(table_no)
        if source_type:
            clauses.append("m.source_type=?")
            params.append(source_type)
        sql = """SELECT m.*,mc.chapter_id AS assigned_chapter_id,mb.block_id AS assigned_block_id
                 FROM admin_mapping_rules m
                 LEFT JOIN admin_mapping_chapters mc ON mc.mapping_id=m.id
                 LEFT JOIN admin_mapping_blocks mb ON mb.mapping_id=m.id"""
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY CASE WHEN m.table_no='HEADER' THEN 0 ELSE CAST(SUBSTR(m.table_no,2) AS INTEGER) END, m.id"
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(sql, params).fetchall()]
        return [self._mapping_to_api(row) for row in rows]

    @staticmethod
    def _identifier_segment(value: Any, fallback: str, max_length: int = 48) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
        normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")
        return (normalized or fallback)[:max_length]

    @staticmethod
    def _is_temporary_identifier(value: Any) -> bool:
        current = str(value or "").strip()
        return (
            not current
            or current.isdigit()
            or current.startswith("draft.")
            or re.fullmatch(r"(?:word\.)?contentcontrol\.\d+", current, re.IGNORECASE) is not None
            or re.fullmatch(r"report\..+\.mapping\.\d+", current) is not None
        )

    def ensure_mapping_identifiers(self, item: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        """Generate stable, readable mapping identifiers even for old API clients."""
        result = dict(item)
        with self.database.connect() as connection:
            existing = None
            if rule_id is not None:
                row = connection.execute(
                    "SELECT * FROM admin_mapping_rules WHERE id=?", (rule_id,)
                ).fetchone()
                existing = dict(row) if row else None

            chapter_id = result.get("chapterId")
            if not chapter_id and rule_id is not None:
                row = connection.execute(
                    "SELECT chapter_id FROM admin_mapping_chapters WHERE mapping_id=?", (rule_id,)
                ).fetchone()
                chapter_id = row[0] if row else None
            chapter = connection.execute(
                "SELECT code,title FROM admin_template_chapters WHERE id=?", (chapter_id,)
            ).fetchone() if chapter_id else None

            block_id = result.get("blockId")
            if not block_id and rule_id is not None:
                row = connection.execute(
                    "SELECT block_id FROM admin_mapping_blocks WHERE mapping_id=?", (rule_id,)
                ).fetchone()
                block_id = row[0] if row else None
            block = connection.execute(
                "SELECT title FROM admin_content_blocks WHERE id=?", (block_id,)
            ).fetchone() if block_id else None

            label = str(result.get("wordLabel") or (existing or {}).get("word_label") or "").strip()
            if not label:
                label = f"{block['title']}字段" if block else "未命名字段"
            result["wordLabel"] = label

            raw_section = str(result.get("sectionCode") or (existing or {}).get("section_code") or (chapter["code"] if chapter else "field"))
            section = self._identifier_segment(raw_section, "field")
            if raw_section not in {"cover", "headerFooter"}:
                section = f"s{section}"
            field = self._identifier_segment(label, f"field_{rule_id or 'new'}")
            block_name = self._identifier_segment(block["title"], "") if block else ""
            parts = ["report", section]
            if block_name and block_name != field:
                parts.append(block_name)
            parts.append(field)
            generated_code = ".".join(parts)

            current_code = result.get("fieldCode", (existing or {}).get("field_code", ""))
            field_code = generated_code if self._is_temporary_identifier(current_code) else str(current_code)
            duplicate = connection.execute(
                "SELECT id FROM admin_mapping_rules WHERE field_code=? AND (? IS NULL OR id<>?) LIMIT 1",
                (field_code, rule_id, rule_id),
            ).fetchone()
            if duplicate:
                field_code = f"{generated_code}.m{rule_id or duplicate['id'] + 1}"
            result["fieldCode"] = field_code

            current_tag = result.get("controlTag", (existing or {}).get("control_tag", ""))
            control_tag = f"cc.{field_code}" if self._is_temporary_identifier(current_tag) else str(current_tag)
            result["controlTag"] = control_tag

            current_location = result.get("locationId", (existing or {}).get("location_id", ""))
            if self._is_temporary_identifier(current_location) or not current_location:
                current_location = f"word.content_control.{control_tag}"
            duplicate = connection.execute(
                "SELECT id FROM admin_mapping_rules WHERE location_id=? AND (? IS NULL OR id<>?) LIMIT 1",
                (current_location, rule_id, rule_id),
            ).fetchone()
            if duplicate:
                current_location = f"word.content_control.{control_tag}.m{rule_id or duplicate['id'] + 1}"
            result["locationId"] = str(current_location)
        return result

    def validate_calculation_mapping(self, item: dict[str, Any], rule_id: int | None = None) -> None:
        if item.get("sourceType") != "CALCULATED":
            return
        expression = str(item.get("calculationExpression") or "").strip()
        # Older template mappings used CALCULATED as a classification while still
        # reading a prepared value from sourcePath. They remain valid until edited
        # into an explicit formula by the template designer.
        if not expression and item.get("sourcePath"):
            return
        dependencies = [str(value) for value in item.get("calculationDependencies", [])]
        validate_calculation(expression, dependencies)
        mappings = self.list_mappings()
        known_codes = {mapping["fieldCode"] for mapping in mappings if mapping["id"] != rule_id}
        unknown = [value for value in dependencies if value not in known_codes]
        if unknown:
            raise ValueError(f"依赖字段不存在：{', '.join(unknown)}")
        field_code = str(item.get("fieldCode") or "")
        if field_code in dependencies:
            raise ValueError("计算字段不能依赖自身")

        graph = {
            mapping["fieldCode"]: list(mapping.get("calculationDependencies", []))
            for mapping in mappings
            if mapping.get("sourceType") == "CALCULATED" and mapping["id"] != rule_id
        }
        graph[field_code] = dependencies
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(code: str) -> None:
            if code in visiting:
                raise ValueError("计算字段存在循环依赖")
            if code in visited or code not in graph:
                return
            visiting.add(code)
            for dependency in graph[code]:
                visit(dependency)
            visiting.remove(code)
            visited.add(code)

        visit(field_code)

    def create_mapping(self, item: dict[str, Any]) -> dict[str, Any]:
        item = self.ensure_mapping_identifiers(item)
        self.validate_calculation_mapping(item)
        if item.get("sourceType") == "CALCULATED" and item.get("calculationExpression"):
            item["sourcePath"] = ""
        values = {db: item.get(api, False if api in {"required", "sourcePending", "enabled"} else "")
                  for api, db in MAPPING_COLUMNS.items()}
        values["calculation_dependencies"] = json.dumps(
            item.get("calculationDependencies", []), ensure_ascii=False
        )
        values["calculation_scope"] = item.get("calculationScope", "REPORT")
        values["calculation_precision"] = int(item.get("calculationPrecision", 2))
        values["calculation_null_behavior"] = item.get("calculationNullBehavior", "ERROR")
        values["enabled"] = item.get("enabled", True)
        values["updated_at"] = now_iso()
        columns = ",".join(values)
        placeholders = ",".join("?" for _ in values)
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"INSERT INTO admin_mapping_rules({columns}) VALUES({placeholders})", tuple(values.values())
            )
            row = connection.execute("SELECT * FROM admin_mapping_rules WHERE id=?", (cursor.lastrowid,)).fetchone()
        if item.get("chapterId"):
            with self.database.connect() as connection:
                connection.execute("INSERT OR REPLACE INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(?,?)", (cursor.lastrowid, item["chapterId"]))
        if item.get("blockId"):
            with self.database.connect() as connection:
                order_no = connection.execute(
                    "SELECT COALESCE(MAX(order_no),-1)+1 FROM admin_mapping_blocks WHERE block_id=?",
                    (item["blockId"],),
                ).fetchone()[0]
                connection.execute(
                    "INSERT OR REPLACE INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(?,?,?)",
                    (cursor.lastrowid, item["blockId"], order_no),
                )
        elif item.get("chapterId"):
            block = self.create_content_block({
                "chapterId": item["chapterId"], "title": item.get("wordLabel") or "字段组",
                "kind": "MAPPED_FIELD", "tableNo": "", "enabled": True,
            })
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(?,?,0)",
                    (cursor.lastrowid, block["id"]),
                )
        return next((value for value in self.list_mappings() if value["id"] == cursor.lastrowid), self._mapping_to_api(dict(row)))

    def update_mapping(self, rule_id: int, item: dict[str, Any]) -> dict[str, Any] | None:
        item = self.ensure_mapping_identifiers(item, rule_id)
        self.validate_calculation_mapping(item, rule_id)
        if item.get("sourceType") == "CALCULATED" and item.get("calculationExpression"):
            item["sourcePath"] = ""
        values = {db: item[api] for api, db in MAPPING_COLUMNS.items() if api in item}
        if "calculationDependencies" in item:
            values["calculation_dependencies"] = json.dumps(
                item.get("calculationDependencies", []), ensure_ascii=False
            )
        values["updated_at"] = now_iso()
        assignments = ",".join(f"{key}=?" for key in values)
        with self.database.connect() as connection:
            connection.execute(f"UPDATE admin_mapping_rules SET {assignments} WHERE id=?", (*values.values(), rule_id))
            row = connection.execute("SELECT * FROM admin_mapping_rules WHERE id=?", (rule_id,)).fetchone()
            if "chapterId" in item:
                if item.get("chapterId"):
                    connection.execute("INSERT OR REPLACE INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(?,?)", (rule_id, item["chapterId"]))
                else:
                    connection.execute("DELETE FROM admin_mapping_chapters WHERE mapping_id=?", (rule_id,))
            if "blockId" in item:
                if item.get("blockId"):
                    current = connection.execute(
                        "SELECT block_id FROM admin_mapping_blocks WHERE mapping_id=?", (rule_id,)
                    ).fetchone()
                    if not current or int(current["block_id"]) != int(item["blockId"]):
                        order_no = connection.execute(
                            "SELECT COALESCE(MAX(order_no),-1)+1 FROM admin_mapping_blocks WHERE block_id=?",
                            (item["blockId"],),
                        ).fetchone()[0]
                        connection.execute(
                            "INSERT OR REPLACE INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(?,?,?)",
                            (rule_id, item["blockId"], order_no),
                        )
                else:
                    connection.execute("DELETE FROM admin_mapping_blocks WHERE mapping_id=?", (rule_id,))
        return next((value for value in self.list_mappings() if value["id"] == rule_id), self._mapping_to_api(dict(row))) if row else None

    def delete_mapping(self, rule_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_mapping_rules WHERE id=?", (rule_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _content_block_to_api(row: dict[str, Any], mapping_ids: list[int] | None = None) -> dict[str, Any]:
        return {
            "id": row["id"], "chapterId": row["chapter_id"], "title": row["title"],
            "kind": row["kind"], "tableNo": row["table_no"], "orderNo": row["order_no"],
            "sourcePath": row.get("source_path", ""), "repeatKey": row.get("repeat_key", ""),
            "prototypeLocation": row.get("prototype_location", ""), "dedupKey": row.get("dedup_key", ""),
            "sortRule": row.get("sort_rule", ""), "emptyBehavior": row.get("empty_behavior", "KEEP"),
            "mergeRule": row.get("merge_rule", "NONE"),
            "enabled": bool(row["enabled"]), "mappingIds": mapping_ids or [], "updatedAt": row["updated_at"],
        }

    def list_content_blocks(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_content_blocks ORDER BY chapter_id,order_no,id"
            ).fetchall()]
            mapping_rows = connection.execute(
                "SELECT block_id,mapping_id FROM admin_mapping_blocks ORDER BY block_id,order_no,mapping_id"
            ).fetchall()
        mapping_ids: dict[int, list[int]] = defaultdict(list)
        for item in mapping_rows:
            mapping_ids[int(item["block_id"])].append(int(item["mapping_id"]))
        return [self._content_block_to_api(row, mapping_ids.get(int(row["id"]), [])) for row in rows]

    def reorder_content_blocks(self, chapter_id: int, block_ids: list[int]) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            existing = [
                int(row["id"]) for row in connection.execute(
                    "SELECT id FROM admin_content_blocks WHERE chapter_id=? ORDER BY order_no,id",
                    (chapter_id,),
                ).fetchall()
            ]
            if len(block_ids) != len(existing) or set(block_ids) != set(existing):
                raise ValueError("内容块顺序与当前章节不一致，请刷新后重试")
            connection.executemany(
                "UPDATE admin_content_blocks SET order_no=?,updated_at=? WHERE id=?",
                [(order_no, now_iso(), block_id) for order_no, block_id in enumerate(block_ids)],
            )
        return [item for item in self.list_content_blocks() if item["chapterId"] == chapter_id]

    def reorder_block_mappings(self, block_id: int, mapping_ids: list[int]) -> list[int]:
        with self.database.connect() as connection:
            existing = [
                int(row["mapping_id"]) for row in connection.execute(
                    "SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=? ORDER BY order_no,mapping_id",
                    (block_id,),
                ).fetchall()
            ]
            if len(mapping_ids) != len(existing) or set(mapping_ids) != set(existing):
                raise ValueError("字段顺序与当前内容块不一致，请刷新后重试")
            connection.executemany(
                "UPDATE admin_mapping_blocks SET order_no=? WHERE mapping_id=? AND block_id=?",
                [(order_no, mapping_id, block_id) for order_no, mapping_id in enumerate(mapping_ids)],
            )
        return mapping_ids

    def create_content_block(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.database.connect() as connection:
            order_no = item.get("orderNo")
            if order_no is None:
                order_no = connection.execute(
                    "SELECT COALESCE(MAX(order_no),-1)+1 FROM admin_content_blocks WHERE chapter_id=?",
                    (item["chapterId"],),
                ).fetchone()[0]
            cursor = connection.execute(
                """INSERT INTO admin_content_blocks(chapter_id,title,kind,table_no,source_path,repeat_key,
                   prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item["chapterId"], item["title"], item.get("kind", "MAPPED_FIELD"),
                 item.get("tableNo", ""), item.get("sourcePath", ""), item.get("repeatKey", ""),
                 item.get("prototypeLocation", ""), item.get("dedupKey", ""), item.get("sortRule", ""),
                 item.get("emptyBehavior", "KEEP"), item.get("mergeRule", "NONE"), order_no,
                 int(item.get("enabled", True)), now_iso()),
            )
        return next(value for value in self.list_content_blocks() if value["id"] == cursor.lastrowid)

    def update_content_block(self, block_id: int, item: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"chapterId": "chapter_id", "title": "title", "kind": "kind", "tableNo": "table_no",
                   "sourcePath": "source_path", "repeatKey": "repeat_key",
                   "prototypeLocation": "prototype_location", "dedupKey": "dedup_key",
                   "sortRule": "sort_rule", "emptyBehavior": "empty_behavior", "mergeRule": "merge_rule",
                   "orderNo": "order_no", "enabled": "enabled"}
        values = {column: int(item[key]) if key == "enabled" else item[key]
                  for key, column in allowed.items() if key in item}
        values["updated_at"] = now_iso()
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE admin_content_blocks SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                (*values.values(), block_id),
            )
            kind = item.get("kind") or connection.execute(
                "SELECT kind FROM admin_content_blocks WHERE id=?", (block_id,)
            ).fetchone()[0]
            if kind in {"REPEATING_TABLE", "MATRIX"}:
                connection.execute(
                    """UPDATE admin_mapping_rules SET table_no=?,repeat_type='ROW',repeat_key=?,updated_at=?
                       WHERE id IN (SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=?)""",
                    (item.get("tableNo", ""), item.get("repeatKey", ""), now_iso(), block_id),
                )
            elif "kind" in item:
                connection.execute(
                    """UPDATE admin_mapping_rules SET repeat_type='NONE',repeat_key='',updated_at=?
                       WHERE id IN (SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=?)""",
                    (now_iso(), block_id),
                )
        return next((value for value in self.list_content_blocks() if value["id"] == block_id), None)

    def delete_content_block(self, block_id: int, delete_mappings: bool = True) -> bool:
        with self.database.connect() as connection:
            row = connection.execute("SELECT id FROM admin_content_blocks WHERE id=?", (block_id,)).fetchone()
            if not row:
                return False
            if delete_mappings:
                connection.execute(
                    "DELETE FROM admin_mapping_rules WHERE id IN (SELECT mapping_id FROM admin_mapping_blocks WHERE block_id=?)",
                    (block_id,),
                )
            connection.execute("DELETE FROM admin_content_blocks WHERE id=?", (block_id,))
        return True

    @staticmethod
    def _chapter_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "parentId": row["parent_id"], "code": row["code"], "title": row["title"],
                "pageHint": row["page_hint"], "orderNo": row["order_no"], "enabled": bool(row["enabled"]),
                "updatedAt": row["updated_at"]}

    def list_template_chapters(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM admin_template_chapters ORDER BY order_no,id").fetchall()]
        return [self._chapter_to_api(row) for row in rows]

    def create_template_chapter(self, item: dict[str, Any]) -> dict[str, Any]:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO admin_template_chapters(parent_id,code,title,page_hint,order_no,enabled,updated_at) VALUES(?,?,?,?,?,?,?)",
                (item.get("parentId"), item["code"], item["title"], item.get("pageHint"), item.get("orderNo", 999), int(item.get("enabled", True)), now_iso()),
            )
            row = connection.execute("SELECT * FROM admin_template_chapters WHERE id=?", (cursor.lastrowid,)).fetchone()
        return self._chapter_to_api(dict(row))

    def update_template_chapter(self, chapter_id: int, item: dict[str, Any]) -> dict[str, Any] | None:
        fields = {"parent_id": item["parentId"] if "parentId" in item else None,
                  "code": item["code"] if "code" in item else None, "title": item["title"] if "title" in item else None,
                  "page_hint": item["pageHint"] if "pageHint" in item else None, "order_no": item["orderNo"] if "orderNo" in item else None,
                  "enabled": int(item["enabled"]) if "enabled" in item else None}
        fields = {key: value for key, value in fields.items() if value is not None}
        if not fields:
            return next((value for value in self.list_template_chapters() if value["id"] == chapter_id), None)
        fields["updated_at"] = now_iso()
        with self.database.connect() as connection:
            connection.execute(f"UPDATE admin_template_chapters SET {','.join(f'{key}=?' for key in fields)} WHERE id=?", (*fields.values(), chapter_id))
            row = connection.execute("SELECT * FROM admin_template_chapters WHERE id=?", (chapter_id,)).fetchone()
        return self._chapter_to_api(dict(row)) if row else None

    def delete_template_chapter(self, chapter_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_template_chapters WHERE id=?", (chapter_id,))
        return cursor.rowcount > 0

    def list_table_rules(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_table_rules ORDER BY CAST(SUBSTR(table_no,2) AS INTEGER)"
            ).fetchall()]
        return [self._table_to_api(row) for row in rows]

    @staticmethod
    def _table_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "tableNo": row["table_no"], "sectionCode": row["section_code"], "mode": row["mode"],
            "headerRows": row["header_rows"], "dataRowStart": row["data_row_start"],
            "dataRowEnd": row["data_row_end"], "footerRows": row["footer_rows"],
            "recordKey": row["record_key"], "mergeFields": json.loads(row["merge_fields"]),
            "enabled": bool(row["enabled"]), "notes": row["notes"], "updatedAt": row["updated_at"],
        }

    def upsert_table_rule(self, item: dict[str, Any]) -> dict[str, Any]:
        values = (
            item["tableNo"], item.get("sectionCode", ""), item.get("mode", "ROW_REPEAT"),
            item.get("headerRows", 1), item.get("dataRowStart", 2), item.get("dataRowEnd", 2),
            item.get("footerRows", 0), item.get("recordKey", ""),
            json.dumps(item.get("mergeFields", []), ensure_ascii=False), int(item.get("enabled", True)),
            item.get("notes", ""), now_iso(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_table_rules(table_no,section_code,mode,header_rows,data_row_start,data_row_end,
                   footer_rows,record_key,merge_fields,enabled,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(table_no) DO UPDATE SET section_code=excluded.section_code,mode=excluded.mode,
                   header_rows=excluded.header_rows,data_row_start=excluded.data_row_start,data_row_end=excluded.data_row_end,
                   footer_rows=excluded.footer_rows,record_key=excluded.record_key,merge_fields=excluded.merge_fields,
                   enabled=excluded.enabled,notes=excluded.notes,updated_at=excluded.updated_at""", values,
            )
            row = connection.execute("SELECT * FROM admin_table_rules WHERE table_no=?", (item["tableNo"],)).fetchone()
        return self._table_to_api(dict(row))

    def list_data_sources(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM admin_data_sources ORDER BY priority").fetchall()]
        return [{"id": row["id"], "code": row["code"], "name": row["name"], "sourceType": row["source_type"],
                 "priority": row["priority"], "enabled": bool(row["enabled"]), "config": json.loads(row["config"]),
                 "updatedAt": row["updated_at"]} for row in rows]

    def upsert_data_source(self, item: dict[str, Any]) -> dict[str, Any]:
        values = (item["code"], item["name"], item["sourceType"], item.get("priority", 100),
                  int(item.get("enabled", True)), json.dumps(item.get("config", {}), ensure_ascii=False), now_iso())
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_data_sources(code,name,source_type,priority,enabled,config,updated_at) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name,source_type=excluded.source_type,
                   priority=excluded.priority,enabled=excluded.enabled,config=excluded.config,updated_at=excluded.updated_at""", values,
            )
            row = connection.execute("SELECT * FROM admin_data_sources WHERE code=?", (item["code"],)).fetchone()
        result = dict(row)
        return {"id": result["id"], "code": result["code"], "name": result["name"],
                "sourceType": result["source_type"], "priority": result["priority"],
                "enabled": bool(result["enabled"]), "config": json.loads(result["config"]), "updatedAt": result["updated_at"]}

    def list_ai_rules(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM admin_ai_rules ORDER BY field_code").fetchall()]
        return [self._ai_to_api(row) for row in rows]

    @staticmethod
    def _ai_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "fieldCode": row["field_code"], "name": row["name"],
                "inputFields": json.loads(row["input_fields"]), "promptTemplate": row["prompt_template"],
                "outputType": row["output_type"], "maxLength": row["max_length"],
                "requireCitations": bool(row["require_citations"]), "requiresApproval": bool(row["requires_approval"]),
                "provider": row["provider"], "model": row["model"], "enabled": bool(row["enabled"]),
                "updatedAt": row["updated_at"]}

    def upsert_ai_rule(self, item: dict[str, Any]) -> dict[str, Any]:
        values = (item["fieldCode"], item["name"], json.dumps(item.get("inputFields", []), ensure_ascii=False),
                  item.get("promptTemplate", ""), item.get("outputType", "richText"), item.get("maxLength", 500),
                  int(item.get("requireCitations", True)), int(item.get("requiresApproval", True)),
                  item.get("provider", "unconfigured"), item.get("model", ""), int(item.get("enabled", True)), now_iso())
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO admin_ai_rules(field_code,name,input_fields,prompt_template,output_type,max_length,
                   require_citations,requires_approval,provider,model,enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(field_code) DO UPDATE SET name=excluded.name,input_fields=excluded.input_fields,
                   prompt_template=excluded.prompt_template,output_type=excluded.output_type,max_length=excluded.max_length,
                   require_citations=excluded.require_citations,requires_approval=excluded.requires_approval,
                   provider=excluded.provider,model=excluded.model,enabled=excluded.enabled,updated_at=excluded.updated_at""", values,
            )
            row = connection.execute("SELECT * FROM admin_ai_rules WHERE field_code=?", (item["fieldCode"],)).fetchone()
        return self._ai_to_api(dict(row))

    def delete_ai_rule(self, rule_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_ai_rules WHERE id=?", (rule_id,))
        return cursor.rowcount > 0

    def snapshot(self) -> dict[str, Any]:
        return {"mappings": self.list_mappings(), "tableRules": self.list_table_rules(),
                "dataSources": self.list_data_sources(), "aiRules": self.list_ai_rules(),
                "chapters": self.list_template_chapters(), "contentBlocks": self.list_content_blocks()}

    def active_workspace(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT w.active_template_id,w.active_version_id,t.name AS template_name,
                   v.version_no,v.status AS version_status,v.template_file
                   FROM admin_template_workspace w
                   JOIN admin_templates t ON t.id=w.active_template_id
                   JOIN admin_template_versions v ON v.id=w.active_version_id WHERE w.id=1"""
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        return {"templateId": item["active_template_id"], "versionId": item["active_version_id"],
                "templateName": item["template_name"], "versionNo": item["version_no"],
                "versionStatus": item["version_status"], "templateFile": item["template_file"]}

    def save_active_workspace(self, template_file: str | None = None) -> None:
        active = self.active_workspace()
        if not active:
            return
        snapshot = self.snapshot()
        with self.database.connect() as connection:
            if template_file is None:
                connection.execute(
                    "UPDATE admin_template_versions SET snapshot=?,updated_at=? WHERE id=?",
                    (json.dumps(snapshot, ensure_ascii=False), now_iso(), active["versionId"]),
                )
            else:
                connection.execute(
                    "UPDATE admin_template_versions SET snapshot=?,template_file=?,updated_at=? WHERE id=?",
                    (json.dumps(snapshot, ensure_ascii=False), template_file, now_iso(), active["versionId"]),
                )

    def _restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        chapters = snapshot.get("chapters") or self.list_template_chapters()
        mappings = snapshot.get("mappings", [])
        with self.database.connect() as connection:
            connection.execute("DELETE FROM admin_mapping_blocks")
            connection.execute("DELETE FROM admin_content_blocks")
            connection.execute("DELETE FROM admin_mapping_chapters")
            connection.execute("DELETE FROM admin_mapping_rules")
            connection.execute("DELETE FROM admin_template_chapters")
            connection.execute("DELETE FROM admin_table_rules")
            connection.execute("DELETE FROM admin_ai_rules")
            for item in sorted(chapters, key=lambda value: (value.get("orderNo", 0), value.get("id", 0))):
                connection.execute(
                    """INSERT INTO admin_template_chapters(id,parent_id,code,title,page_hint,order_no,enabled,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (item["id"], item.get("parentId"), item["code"], item["title"], item.get("pageHint"),
                     item.get("orderNo", 0), int(item.get("enabled", True)), now_iso()),
                )
            for item in mappings:
                values = [item.get(api, False if api in {"required", "sourcePending"} else True if api == "enabled" else "")
                          for api in MAPPING_COLUMNS]
                dependency_index = list(MAPPING_COLUMNS).index("calculationDependencies")
                values[dependency_index] = json.dumps(
                    item.get("calculationDependencies", []), ensure_ascii=False
                )
                values[list(MAPPING_COLUMNS).index("calculationScope")] = item.get(
                    "calculationScope", "REPORT"
                ) or "REPORT"
                values[list(MAPPING_COLUMNS).index("calculationPrecision")] = int(
                    item.get("calculationPrecision", 2) or 2
                )
                values[list(MAPPING_COLUMNS).index("calculationNullBehavior")] = item.get(
                    "calculationNullBehavior", "ERROR"
                ) or "ERROR"
                connection.execute(
                    f"INSERT INTO admin_mapping_rules(id,{','.join(MAPPING_COLUMNS.values())},updated_at) "
                    f"VALUES({','.join('?' for _ in range(len(values) + 2))})",
                    (item["id"], *values, now_iso()),
                )
                if item.get("chapterId"):
                    connection.execute(
                        "INSERT INTO admin_mapping_chapters(mapping_id,chapter_id) VALUES(?,?)",
                        (item["id"], item["chapterId"]),
                    )
            for item in snapshot.get("contentBlocks", []):
                connection.execute(
                    """INSERT INTO admin_content_blocks(id,chapter_id,title,kind,table_no,source_path,repeat_key,
                       prototype_location,dedup_key,sort_rule,empty_behavior,merge_rule,order_no,enabled,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item["id"], item["chapterId"], item["title"], item.get("kind", "MAPPED_FIELD"),
                     item.get("tableNo", ""), item.get("sourcePath", ""), item.get("repeatKey", ""),
                     item.get("prototypeLocation", ""), item.get("dedupKey", ""), item.get("sortRule", ""),
                     item.get("emptyBehavior", "KEEP"), item.get("mergeRule", "NONE"), item.get("orderNo", 0),
                     int(item.get("enabled", True)), now_iso()),
                )
                connection.executemany(
                    "INSERT INTO admin_mapping_blocks(mapping_id,block_id,order_no) VALUES(?,?,?)",
                    [
                        (mapping_id, item["id"], order_no)
                        for order_no, mapping_id in enumerate(item.get("mappingIds", []))
                    ],
                )
            for item in snapshot.get("tableRules", []):
                connection.execute(
                    """INSERT INTO admin_table_rules(table_no,section_code,mode,header_rows,data_row_start,data_row_end,
                       footer_rows,record_key,merge_fields,enabled,notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item["tableNo"], item.get("sectionCode", ""), item.get("mode", "ROW_REPEAT"),
                     item.get("headerRows", 1), item.get("dataRowStart", 2), item.get("dataRowEnd", 2),
                     item.get("footerRows", 0), item.get("recordKey", ""),
                     json.dumps(item.get("mergeFields", []), ensure_ascii=False), int(item.get("enabled", True)),
                     item.get("notes", ""), now_iso()),
                )
            for item in snapshot.get("aiRules", []):
                connection.execute(
                    """INSERT INTO admin_ai_rules(id,field_code,name,input_fields,prompt_template,output_type,max_length,
                       require_citations,requires_approval,provider,model,enabled,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (item.get("id"), item["fieldCode"], item["name"],
                     json.dumps(item.get("inputFields", []), ensure_ascii=False), item.get("promptTemplate", ""),
                     item.get("outputType", "richText"), item.get("maxLength", 500),
                     int(item.get("requireCitations", True)), int(item.get("requiresApproval", True)),
                     item.get("provider", "unconfigured"), item.get("model", ""),
                    int(item.get("enabled", True)), now_iso()),
                )
        if not snapshot.get("contentBlocks"):
            self._seed_content_blocks()

    @staticmethod
    def _catalog_version_to_api(row: dict[str, Any]) -> dict[str, Any]:
        validation = json.loads(row.get("validation_report") or "{}")
        return {"id": row["id"], "templateId": row["template_id"], "versionNo": row["version_no"],
                "status": row["status"], "note": row["note"], "templateFile": row.get("template_file"),
                "validationReport": validation, "createdAt": row["created_at"], "updatedAt": row["updated_at"],
                "publishedAt": row.get("published_at")}

    def list_templates(self) -> list[dict[str, Any]]:
        active = self.active_workspace()
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT t.*,COUNT(v.id) AS version_count,MAX(v.version_no) AS latest_version,
                   MAX(CASE WHEN v.status='PUBLISHED' THEN v.version_no END) AS published_version
                   FROM admin_templates t LEFT JOIN admin_template_versions v ON v.template_id=t.id
                   GROUP BY t.id ORDER BY t.updated_at DESC"""
            ).fetchall()]
        return [{"id": row["id"], "code": row["code"], "name": row["name"],
                 "description": row["description"], "status": row["status"],
                 "versionCount": row["version_count"], "latestVersion": row["latest_version"],
                 "publishedVersion": row["published_version"], "createdAt": row["created_at"],
                 "updatedAt": row["updated_at"], "active": bool(active and active["templateId"] == row["id"])}
                for row in rows]

    def create_template(self, item: dict[str, Any], template_file: str | None = None) -> dict[str, Any]:
        template_id = uuid.uuid4().hex
        version_id = uuid.uuid4().hex
        timestamp = now_iso()
        snapshot = item.get("snapshot") or self.snapshot()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO admin_templates(id,code,name,description,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (template_id, item["code"], item["name"], item.get("description", ""), "ACTIVE", timestamp, timestamp),
            )
            connection.execute(
                """INSERT INTO admin_template_versions(id,template_id,version_no,status,note,snapshot,template_file,
                   validation_report,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (version_id, template_id, 1, "DRAFT", item.get("note", "初始版本"),
                 json.dumps(snapshot, ensure_ascii=False), template_file, "{}", timestamp, timestamp),
            )
        return next(value for value in self.list_templates() if value["id"] == template_id)

    def update_template(self, template_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"code": "code", "name": "name", "description": "description", "status": "status"}
        values = {column: item[key] for key, column in allowed.items() if key in item}
        if values:
            values["updated_at"] = now_iso()
            with self.database.connect() as connection:
                connection.execute(
                    f"UPDATE admin_templates SET {','.join(f'{key}=?' for key in values)} WHERE id=?",
                    (*values.values(), template_id),
                )
        return next((value for value in self.list_templates() if value["id"] == template_id), None)

    def delete_template(self, template_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            template = connection.execute(
                "SELECT id,name FROM admin_templates WHERE id=?", (template_id,)
            ).fetchone()
            if not template:
                raise ValueError("模板不存在")
            if connection.execute("SELECT COUNT(*) FROM admin_templates").fetchone()[0] <= 1:
                raise ValueError("系统至少需要保留一个报告模板")
            version_ids = [
                row["id"] for row in connection.execute(
                    "SELECT id FROM admin_template_versions WHERE template_id=?", (template_id,)
                ).fetchall()
            ]

        active = self.active_workspace()
        if active and active["templateId"] == template_id:
            with self.database.connect() as connection:
                fallback = connection.execute(
                    """SELECT t.id AS template_id,v.id AS version_id
                       FROM admin_templates t
                       JOIN admin_template_versions v ON v.template_id=t.id
                       WHERE t.id<>?
                       ORDER BY t.updated_at DESC,v.version_no DESC LIMIT 1""",
                    (template_id,),
                ).fetchone()
            if not fallback:
                raise ValueError("没有可切换的备用模板版本")
            self.activate_template_version(fallback["template_id"], fallback["version_id"])

        with self.database.connect() as connection:
            connection.execute("DELETE FROM admin_templates WHERE id=?", (template_id,))
        return {"id": template_id, "name": template["name"], "versionIds": version_ids}

    def list_template_versions(self, template_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_template_versions WHERE template_id=? ORDER BY version_no DESC", (template_id,)
            ).fetchall()]
        return [self._catalog_version_to_api(row) for row in rows]

    def get_template_version(self, version_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM admin_template_versions WHERE id=?", (version_id,)
            ).fetchone()
        return self._catalog_version_to_api(dict(row)) if row else None

    def set_template_version_file(self, version_id: str, template_file: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE admin_template_versions SET template_file=?,updated_at=? WHERE id=?",
                (template_file, now_iso(), version_id),
            )
        return cursor.rowcount > 0

    def create_template_version(self, template_id: str, base_version_id: str | None,
                                note: str, template_file: str | None = None) -> dict[str, Any]:
        if base_version_id:
            with self.database.connect() as connection:
                base = connection.execute(
                    "SELECT snapshot,template_file FROM admin_template_versions WHERE id=? AND template_id=?",
                    (base_version_id, template_id),
                ).fetchone()
            if not base:
                raise ValueError("基础版本不存在")
            snapshot = json.loads(base["snapshot"])
            source_file = base["template_file"]
        else:
            snapshot, source_file = self.snapshot(), None
        timestamp = now_iso()
        version_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            version_no = connection.execute(
                "SELECT COALESCE(MAX(version_no),0)+1 FROM admin_template_versions WHERE template_id=?", (template_id,)
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO admin_template_versions(id,template_id,version_no,status,note,snapshot,template_file,
                   validation_report,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (version_id, template_id, version_no, "DRAFT", note or f"版本 {version_no}",
                 json.dumps(snapshot, ensure_ascii=False), template_file or source_file, "{}", timestamp, timestamp),
            )
            connection.execute("UPDATE admin_templates SET updated_at=? WHERE id=?", (timestamp, template_id))
        return next(value for value in self.list_template_versions(template_id) if value["id"] == version_id)

    def activate_template_version(self, template_id: str, version_id: str) -> dict[str, Any]:
        active = self.active_workspace()
        if active and active["versionId"] != version_id:
            self.save_active_workspace()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM admin_template_versions WHERE id=? AND template_id=?", (version_id, template_id)
            ).fetchone()
        if not row:
            raise ValueError("模板版本不存在")
        if not active or active["versionId"] != version_id:
            self._restore_snapshot(json.loads(row["snapshot"]))
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO admin_template_workspace(id,active_template_id,active_version_id,updated_at) VALUES(1,?,?,?)",
                (template_id, version_id, now_iso()),
            )
        return self.active_workspace() or {}

    def publish_active_template_version(self, snapshot: dict[str, Any], validation: dict[str, Any],
                                        compiled_template: str) -> dict[str, Any]:
        active = self.active_workspace()
        if not active:
            raise ValueError("没有活动模板版本")
        timestamp = now_iso()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE admin_template_versions SET status='ARCHIVED' WHERE template_id=? AND status='PUBLISHED' AND id<>?",
                (active["templateId"], active["versionId"]),
            )
            connection.execute(
                """UPDATE admin_template_versions SET status='PUBLISHED',snapshot=?,validation_report=?,
                   template_file=?,updated_at=?,published_at=? WHERE id=?""",
                (json.dumps(snapshot, ensure_ascii=False), json.dumps(validation, ensure_ascii=False),
                 compiled_template, timestamp, timestamp, active["versionId"]),
            )
            connection.execute("UPDATE admin_templates SET updated_at=? WHERE id=?", (timestamp, active["templateId"]))
            row = connection.execute("SELECT * FROM admin_template_versions WHERE id=?", (active["versionId"],)).fetchone()
        return self._catalog_version_to_api(dict(row))

    def summary(self) -> dict[str, Any]:
        mappings = self.list_mappings()
        table_rules = self.list_table_rules()
        return {
            "mappingCount": len(mappings), "enabledMappings": sum(item["enabled"] for item in mappings),
            "tableCount": len(table_rules), "enabledTables": sum(item["enabled"] for item in table_rules),
            "sourceCounts": dict(Counter(item["sourceType"] for item in mappings)),
            "pendingCount": sum(item["sourcePending"] for item in mappings),
            "aiRuleCount": len(self.list_ai_rules()), "publishedVersion": self.latest_published_version(),
        }

    def latest_published_version(self) -> int | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT MAX(version_no) FROM admin_rule_versions WHERE status='PUBLISHED'").fetchone()
        return row[0] if row and row[0] else None

    def active_runtime_rules(self) -> tuple[dict[str, Any], str | None]:
        with self.database.connect() as connection:
            catalog_row = connection.execute(
                """SELECT v.snapshot,v.template_file FROM admin_template_versions v
                   JOIN admin_template_workspace w ON w.active_template_id=v.template_id
                   WHERE w.id=1 AND v.status='PUBLISHED' ORDER BY v.version_no DESC LIMIT 1"""
            ).fetchone()
            if catalog_row:
                return json.loads(catalog_row["snapshot"]), catalog_row["template_file"]
            row = connection.execute(
                "SELECT snapshot,compiled_template FROM admin_rule_versions "
                "WHERE status='PUBLISHED' ORDER BY version_no DESC LIMIT 1"
            ).fetchone()
        if row:
            return json.loads(row["snapshot"]), row["compiled_template"]
        return self.snapshot(), None

    def create_version(self, snapshot: dict[str, Any], validation: dict[str, Any], compiled_template: str,
                       note: str, publish: bool) -> dict[str, Any]:
        with self.database.connect() as connection:
            version_no = connection.execute("SELECT COALESCE(MAX(version_no),0)+1 FROM admin_rule_versions").fetchone()[0]
            if publish:
                connection.execute("UPDATE admin_rule_versions SET status='ARCHIVED' WHERE status='PUBLISHED'")
            timestamp = now_iso()
            cursor = connection.execute(
                """INSERT INTO admin_rule_versions(version_no,status,note,snapshot,validation_report,compiled_template,
                   created_at,published_at) VALUES(?,?,?,?,?,?,?,?)""",
                (version_no, "PUBLISHED" if publish else "DRAFT", note,
                 json.dumps(snapshot, ensure_ascii=False), json.dumps(validation, ensure_ascii=False),
                 compiled_template, timestamp, timestamp if publish else None),
            )
            row = connection.execute("SELECT * FROM admin_rule_versions WHERE id=?", (cursor.lastrowid,)).fetchone()
        return self._version_to_api(dict(row))

    def list_versions(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM admin_rule_versions ORDER BY version_no DESC"
            ).fetchall()]
        return [self._version_to_api(row) for row in rows]

    @staticmethod
    def _version_to_api(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "versionNo": row["version_no"], "status": row["status"],
                "note": row["note"], "validationReport": json.loads(row["validation_report"]),
                "compiledTemplate": row["compiled_template"], "createdAt": row["created_at"],
                "publishedAt": row["published_at"]}
