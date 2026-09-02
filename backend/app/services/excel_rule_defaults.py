from datetime import datetime, timezone
import json
from typing import Any


EXCEL_FIELD_PATHS = {
    "project.name": "$.project.name",
    "document.version": "$.document.version",
    "impurity.impurityName": "$.impurity[*].impurityName",
    "referenceStandards.name": "$.referenceStandards[*].name",
    "referenceStandards.content": "$.referenceStandards[*].content",
    "systemSuitability.impurityName": "$.systemSuitability[*].impurityName",
    "systemSuitability.solutionName": "$.systemSuitability[*].solutionName",
    "systemSuitability.sequence": "$.systemSuitability[*].sequence",
    "systemSuitability.retentionTime": "$.systemSuitability[*].retentionTime",
    "systemSuitability.peakArea": "$.systemSuitability[*].peakArea",
    "systemSuitability.retentionTimeRsd": "$.systemSuitability[*].retentionTimeRsd",
    "systemSuitability.peakAreaRsd": "$.systemSuitability[*].peakAreaRsd",
    "systemSuitability.conclusion": "$.systemSuitabilityConclusion",
    "specificity.impurityName": "$.specificity[*].impurityName",
    "specificity.solutionName": "$.specificity[*].solutionName",
    "specificity.retentionTime": "$.specificity[*].retentionTime",
    "specificity.peakArea": "$.specificity[*].peakArea",
    "limit.impurityName": "$.limit[*].impurityName",
    "limit.field4": "$.limit[*].field4",
    "limit.field5": "$.limit[*].field5",
    "robustnessSpecificity.solutionName": "$.robustnessSpecificity[*].solutionName",
    "robustnessSpecificity.field2": "$.robustnessSpecificity[*].field2",
    "robustnessSpecificity.field3": "$.robustnessSpecificity[*].field3",
    "uncategorized.field_002": "$.conclusions[*].text",
    "uncategorized.field_005": "$.custom.field_005",
    "uncategorized.field_006": "$.custom.field_006",
    "uncategorized.field_007": "$.lod[*].name",
    "uncategorized.field_008": "$.lod[*].field2",
    "uncategorized.field_009": "$.lod[*].field3",
    "uncategorized.field_010": "$.lod[*].field4",
    "uncategorized.field_011": "$.lod[*].field5",
    "uncategorized.field_012": "$.lod[*].field6",
    "uncategorized.field_013": "$.lod[*].field7",
    "uncategorized.field_014": "$.loq[*].sequence",
    "uncategorized.field_015": "$.loq[*].field2",
    "uncategorized.field_016": "$.loq[*].peakArea",
    "uncategorized.field_017": "$.loq[*].field4",
    "uncategorized.field_018": "$.loq[*].field5",
    "uncategorized.field_019": "$.loq[*].field6",
    "uncategorized.field_020": "$.loq[*].field7",
    "uncategorized.field_021": "$.linearity[*].solutionName",
    "uncategorized.field_022": "$.linearity[*].field2",
    "uncategorized.field_023": "$.linearity[*].peakArea",
    "uncategorized.field_024": "$.linearity[*].regressionEquation",
    "uncategorized.field_025": "$.linearity[*].correlationCoefficient",
    "uncategorized.field_026": "$.linearity[*].interceptRatio",
    "uncategorized.field_027": "$.linearity[*].predictedPeakArea",
    "uncategorized.field_028": "$.linearity[*].residual",
    "uncategorized.field_029": "$.linearity[*].residualChart",
    **{f"uncategorized.field_{index:03d}": f"$.custom.field_{index:03d}" for index in range(30, 43)},
}

EXCEL_WORKBOOK_LOCATIONS = {
    "project.name": {"sheet": "首页", "cells": "B3", "matchBy": "固定单元格", "valueColumn": "B"},
    "document.version": {"sheet": "首页", "cells": "F4", "matchBy": "固定单元格", "valueColumn": "F"},
    "impurity.impurityName": {"sheet": "首页", "cells": "B9:B23", "matchBy": "首页 B8 指定杂质数量", "valueColumn": "B"},
    "referenceStandards.name": {"sheet": "对照品配置", "cells": "A3:A*", "matchBy": "非空数据行", "valueColumn": "A（名称）"},
    "referenceStandards.content": {"sheet": "对照品配置", "cells": "C3:C*", "matchBy": "与名称列同一行", "valueColumn": "C（含量）"},
    "systemSuitability.sequence": {"sheet": "系统适用性", "cells": "固定数据行 3:8", "matchBy": "首页 B9 起的杂质顺序 + 进样序号 1-6", "valueColumn": "按行生成，不读取工作表列"},
    "systemSuitability.solutionName": {"sheet": "系统适用性", "cells": "A3:A8、D3:D8、G3:G8……", "matchBy": "每个杂质对应的系统适用性溶液名称", "valueColumn": "第 3i-2 列"},
    "systemSuitability.retentionTime": {"sheet": "系统适用性", "cells": "B3:B8、E3:E8、H3:H8……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i-1 列（B、E、H、K……）"},
    "systemSuitability.peakArea": {"sheet": "系统适用性", "cells": "C3:C8、F3:F8、I3:I8……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i 列（C、F、I、L……）"},
    "systemSuitability.retentionTimeRsd": {"sheet": "系统适用性", "cells": "B9、E9、H9、K9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "保留时间 RSD"},
    "systemSuitability.peakAreaRsd": {"sheet": "系统适用性", "cells": "C9、F9、I9、L9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "峰面积 RSD"},
    "systemSuitability.conclusion": {"sheet": "系统适用性", "cells": "B10", "matchBy": "固定结论单元格", "valueColumn": "结论"},
    "specificity.impurityName": {"sheet": "专属性", "cells": "每个杂质 5 行分块", "matchBy": "首页杂质名称顺序", "valueColumn": "关联杂质名称"},
    "specificity.solutionName": {"sheet": "专属性", "cells": "B 列，每个杂质块 4 行", "matchBy": "杂质名称分块 + 数据行", "valueColumn": "B（溶液名称）"},
    "specificity.retentionTime": {"sheet": "专属性", "cells": "C 列，每个杂质块 4 行", "matchBy": "杂质名称分块 + 数据行", "valueColumn": "C（保留时间）"},
    "specificity.peakArea": {"sheet": "专属性", "cells": "D 列，每个杂质块 4 行", "matchBy": "杂质名称分块 + 数据行", "valueColumn": "D（峰面积）"},
    "uncategorized.field_005": {"sheet": "系统适用性", "cells": "B9、E9、H9、K9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i-1 列（保留时间 RSD）"},
    "uncategorized.field_006": {"sheet": "系统适用性", "cells": "C9、F9、I9、L9……", "matchBy": "第 i 个杂质对应首页 B(8+i) 的名称", "valueColumn": "第 3i 列（峰面积 RSD）"},
    "uncategorized.field_007": {"sheet": "检测限与定量限", "cells": "C3:C*", "matchBy": "首页 B8 指定杂质数量", "valueColumn": "C（杂质名称）"},
    "uncategorized.field_008": {"sheet": "检测限与定量限", "cells": "D3:D*", "matchBy": "与杂质名称同一行", "valueColumn": "D（S/N-1）"},
    "uncategorized.field_009": {"sheet": "检测限与定量限", "cells": "E3:E*", "matchBy": "与杂质名称同一行", "valueColumn": "E（S/N-2）"},
    "uncategorized.field_010": {"sheet": "检测限与定量限", "cells": "F3:F*", "matchBy": "与杂质名称同一行", "valueColumn": "F（S/N-3）"},
    "uncategorized.field_011": {"sheet": "检测限与定量限", "cells": "G3:G*", "matchBy": "与杂质名称同一行", "valueColumn": "G（检测限浓度）"},
    "uncategorized.field_012": {"sheet": "检测限与定量限", "cells": "H3:H*", "matchBy": "与杂质名称同一行", "valueColumn": "H（相当于供试品中含量）"},
    "uncategorized.field_013": {"sheet": "检测限与定量限", "cells": "I3:I*", "matchBy": "与杂质名称同一行", "valueColumn": "I（占限度百分比）"},
    "uncategorized.field_014": {"sheet": "检测限与定量限", "cells": "D8:D13、D16:D21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "D（No.）"},
    "uncategorized.field_015": {"sheet": "检测限与定量限", "cells": "E8:E13、E16:E21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "E（信噪比 S/N）"},
    "uncategorized.field_016": {"sheet": "检测限与定量限", "cells": "F8:F13、F16:F21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "F（峰面积）"},
    "uncategorized.field_017": {"sheet": "检测限与定量限", "cells": "G8:G13、G16:G21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "G（峰面积 RSD）"},
    "uncategorized.field_018": {"sheet": "检测限与定量限", "cells": "H8:H13、H16:H21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "H（定量限浓度）"},
    "uncategorized.field_019": {"sheet": "检测限与定量限", "cells": "I8:I13、I16:I21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "I（相当于供试品含量）"},
    "uncategorized.field_020": {"sheet": "检测限与定量限", "cells": "J8:J13、J16:J21……", "matchBy": "每个杂质 6 行数据", "valueColumn": "J（占限度百分比）"},
    "uncategorized.field_021": {"sheet": "线性", "cells": "C2:G2、C26:G26……", "matchBy": "每个杂质 5 个水平", "valueColumn": "溶液名称"},
    "uncategorized.field_022": {"sheet": "线性", "cells": "C3:G3、C27:G27……", "matchBy": "每个杂质 5 个水平", "valueColumn": "实际浓度"},
    "uncategorized.field_023": {"sheet": "线性", "cells": "C4:G4、C28:G28……", "matchBy": "每个杂质 5 个水平", "valueColumn": "峰面积"},
    "uncategorized.field_024": {"sheet": "线性", "cells": "由实际浓度与峰面积计算", "matchBy": "每个杂质一条", "valueColumn": "线性回归方程"},
    "uncategorized.field_025": {"sheet": "线性", "cells": "由实际浓度与峰面积计算", "matchBy": "每个杂质一条", "valueColumn": "线性相关系数 R²"},
    "uncategorized.field_026": {"sheet": "线性", "cells": "由实际浓度与峰面积计算", "matchBy": "每个杂质一条", "valueColumn": "截距/100%浓度峰面积"},
    "uncategorized.field_027": {"sheet": "线性", "cells": "C8:G8、C32:G32……", "matchBy": "每个杂质 5 个水平", "valueColumn": "预测峰面积"},
    "uncategorized.field_028": {"sheet": "线性", "cells": "C9:G9、C33:G33……", "matchBy": "每个杂质 5 个水平", "valueColumn": "残差"},
    "uncategorized.field_029": {"sheet": "线性", "cells": "图表对象", "matchBy": "每个杂质的普通线性残差图", "valueColumn": "残差图"},
    "uncategorized.field_030": {"sheet": "重复性跟中间精密度", "cells": "D3:D8、D35:D40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "No"},
    "uncategorized.field_031": {"sheet": "重复性跟中间精密度", "cells": "E3:E8、E35:E40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "E（称样量）"},
    "uncategorized.field_032": {"sheet": "重复性跟中间精密度", "cells": "F3:F8、F35:F40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "保留时间"},
    "uncategorized.field_033": {"sheet": "重复性跟中间精密度", "cells": "G3:G8、G35:G40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "峰面积"},
    "uncategorized.field_034": {"sheet": "重复性跟中间精密度", "cells": "H3:H8、H35:H40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "测得浓度"},
    "uncategorized.field_035": {"sheet": "重复性跟中间精密度", "cells": "I3:I8、I35:I40……", "matchBy": "每个杂质 6 次测定", "valueColumn": "相当供试品中含量"},
    "uncategorized.field_036": {"sheet": "重复性跟中间精密度", "cells": "F9、F42……", "matchBy": "每个杂质汇总行", "valueColumn": "RSD"},
    "uncategorized.field_037": {"sheet": "重复性跟中间精密度", "cells": "F11、F44……", "matchBy": "每个杂质汇总行", "valueColumn": "含量-95%置信下限"},
    "uncategorized.field_038": {"sheet": "重复性跟中间精密度", "cells": "I11、I44……", "matchBy": "每个杂质汇总行", "valueColumn": "含量-95%置信上限"},
    "uncategorized.field_039": {"sheet": "重复性跟中间精密度", "cells": "E10、E43……", "matchBy": "每个杂质汇总行", "valueColumn": "RSD-95%置信下限"},
    "uncategorized.field_040": {"sheet": "重复性跟中间精密度", "cells": "H10、H43……", "matchBy": "每个杂质汇总行", "valueColumn": "RSD-95%置信上限"},
    "uncategorized.field_041": {"sheet": "重复性跟中间精密度", "cells": "F12、F45……", "matchBy": "每个杂质汇总行", "valueColumn": "占理论含量百分比上限"},
    "uncategorized.field_042": {"sheet": "重复性跟中间精密度", "cells": "I12、I45……", "matchBy": "每个杂质汇总行", "valueColumn": "占理论含量百分比下限"},
}


DETECTION_LIMIT_COLUMNS = {
    "uncategorized.field_007": 3,
    "uncategorized.field_008": 4,
    "uncategorized.field_009": 5,
    "uncategorized.field_010": 6,
    "uncategorized.field_011": 7,
    "uncategorized.field_012": 8,
    "uncategorized.field_013": 9,
}

QUANTITATION_LIMIT_COLUMNS = {
    "uncategorized.field_014": 4,
    "uncategorized.field_015": 5,
    "uncategorized.field_016": 6,
    "uncategorized.field_017": 7,
    "uncategorized.field_018": 8,
    "uncategorized.field_019": 9,
    "uncategorized.field_020": 10,
}

LINEARITY_ROWS = {
    "uncategorized.field_021": 2,
    "uncategorized.field_022": 3,
    "uncategorized.field_023": 4,
    "uncategorized.field_027": 8,
    "uncategorized.field_028": 9,
}
LINEARITY_STATISTICS = {
    "uncategorized.field_024": "LINEAR_EQUATION",
    "uncategorized.field_025": "LINEAR_R2",
    "uncategorized.field_026": "LINEAR_INTERCEPT_RATIO",
}

REPEATABILITY_DETAIL_COLUMNS = {
    "uncategorized.field_030": 4, "uncategorized.field_031": 5,
    "uncategorized.field_032": 6, "uncategorized.field_033": 7,
    "uncategorized.field_034": 8, "uncategorized.field_035": 9,
}
REPEATABILITY_SUMMARY_CELLS = {
    "uncategorized.field_036": (9, 6), "uncategorized.field_037": (11, 6),
    "uncategorized.field_038": (11, 9), "uncategorized.field_039": (10, 5),
    "uncategorized.field_040": (10, 8), "uncategorized.field_041": (12, 6),
    "uncategorized.field_042": (12, 9),
}


def _sync_repeated_field_catalog(database: Any, repeated_fields: tuple[str, ...]) -> None:
    with database.connect() as connection:
        placeholders = ",".join("%s" for _ in repeated_fields)
        connection.execute(
            f"UPDATE lims_field_catalog SET cardinality='MANY' WHERE field_code IN ({placeholders})",
            repeated_fields,
        )
        connection.execute(
            f"""UPDATE lims_field_catalog
                SET group_code=(SELECT gf.group_code FROM system_field_group_fields gf
                                WHERE gf.field_code=lims_field_catalog.field_code LIMIT 1)
                WHERE field_code IN ({placeholders})
                  AND EXISTS(SELECT 1 FROM system_field_group_fields gf
                             WHERE gf.field_code=lims_field_catalog.field_code)""",
            repeated_fields,
        )
        connection.execute(
            f"DELETE FROM system_field_chapters WHERE field_code IN ({placeholders})",
            repeated_fields,
        )


def _sync_repeatability_group_chapter(database: Any) -> None:
    with database.connect() as connection:
        group = connection.execute(
            """SELECT DISTINCT gf.group_code FROM system_field_group_fields gf
               WHERE gf.field_code IN ({}) LIMIT 1""".format(
                ",".join("%s" for _ in REPEATABILITY_DETAIL_COLUMNS)
            ), tuple(REPEATABILITY_DETAIL_COLUMNS),
        ).fetchone()
        chapter = connection.execute(
            "SELECT id FROM admin_template_chapters WHERE code='7.5' LIMIT 1"
        ).fetchone()
        if not group or not chapter:
            return
        connection.execute(
            "INSERT IGNORE INTO system_field_group_chapters(group_code,chapter_id) VALUES(%s,%s)",
            (group["group_code"], chapter["id"]),
        )


def _ensure_repeated_field_contracts(database: Any) -> None:
    repeated_fields = (*DETECTION_LIMIT_COLUMNS, *QUANTITATION_LIMIT_COLUMNS,
                       *LINEARITY_ROWS, *LINEARITY_STATISTICS,
                       "uncategorized.field_029",
                       *REPEATABILITY_DETAIL_COLUMNS, *REPEATABILITY_SUMMARY_CELLS)
    _sync_repeated_field_catalog(database, repeated_fields)
    _sync_repeatability_group_chapter(database)


def _sync_excel_field_paths(database: Any) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with database.connect() as connection:
        for field_code, source_path in EXCEL_FIELD_PATHS.items():
            is_residual_chart = field_code == "uncategorized.field_029"
            connection.execute(
                """UPDATE lims_field_catalog SET legacy_json_path=%s,
                   data_type=CASE WHEN %s THEN 'image' ELSE data_type END,updated_at=%s WHERE field_code=%s""",
                (source_path, is_residual_chart, timestamp, field_code),
            )
            connection.execute(
                """UPDATE admin_mapping_rules SET source_path=%s,
                   data_type=CASE WHEN %s THEN 'image' ELSE data_type END,
                   repeat_type=CASE WHEN %s THEN 'NONE' ELSE repeat_type END,
                   location_id=CASE WHEN %s THEN 'body.T20.row9.cell2' ELSE location_id END,
                   source_pending=CASE WHEN %s THEN 0 ELSE source_pending END,
                   fill_rule=CASE WHEN %s THEN 'IMAGE_FIT_WIDE' ELSE fill_rule END,updated_at=%s
                   WHERE standard_field_code=%s""",
                (source_path, is_residual_chart, is_residual_chart, is_residual_chart,
                 is_residual_chart, is_residual_chart, timestamp, field_code),
            )
        versions = connection.execute(
            """SELECT v.id,v.snapshot FROM admin_template_versions v
               JOIN admin_template_workspace w ON w.active_version_id=v.id
               WHERE w.id=1 AND v.status='PUBLISHED'"""
        ).fetchall()
        for version in versions:
            snapshot = json.loads(version["snapshot"] or "{}")
            changed = False
            for mapping in snapshot.get("mappings", []):
                source_path = EXCEL_FIELD_PATHS.get(str(mapping.get("standardFieldCode") or ""))
                if not source_path:
                    continue
                if mapping.get("sourcePath") != source_path or mapping.get("sourceType") != "EXCEL":
                    mapping["sourcePath"] = source_path
                    mapping["sourceType"] = "EXCEL"
                    changed = True
                if str(mapping.get("standardFieldCode") or "") == "uncategorized.field_029":
                    image_values = {
                        "dataType": "image", "repeatType": "NONE", "locationId": "body.T20.row9.cell2",
                        "sourcePending": False, "fillRule": "IMAGE_FIT_WIDE",
                    }
                    for key, value in image_values.items():
                        if mapping.get(key) != value:
                            mapping[key] = value
                            changed = True
            if changed:
                connection.execute(
                    "UPDATE admin_template_versions SET snapshot=%s,updated_at=%s WHERE id=%s",
                    (json.dumps(snapshot, ensure_ascii=False), timestamp, version["id"]),
                )


def _rule_config(field_code: str, source_path: str) -> dict[str, Any]:
    config = {
        "sourcePath": source_path,
        "workbookFormat": "WENXIA_VALIDATION_V49",
        "valueMode": "CACHED",
        "layout": "VBA_FIXED_BLOCKS",
        "workbookLocation": EXCEL_WORKBOOK_LOCATIONS.get(field_code, {}),
    }
    if field_code == "systemSuitability.conclusion":
        config.update({"mode": "FIXED_CELL", "sheet": "系统适用性", "row": 10, "column": 2})
    elif field_code.startswith("systemSuitability."):
        field = field_code.rsplit(".", 1)[-1]
        if field == "impurityName":
            config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 3, "rowEnd": 8,
                           "repeatValueSource": {"sheet": "首页", "row": 9, "column": 2, "rowStep": 1},
                           "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                           "maxRepeat": 15, "valueMode": "REPEAT_VALUE"})
            return config
        if field in {"retentionTimeRsd", "peakAreaRsd"}:
            config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 9, "rowEnd": 9,
                           "startColumn": 2 if field == "retentionTimeRsd" else 3, "columnStep": 3,
                           "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                           "maxRepeat": 15, "valueMode": "CELL", "broadcastRepeat": 6})
            return config
        config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 3, "rowEnd": 8,
                       "startColumn": 2 if field == "retentionTime" else 3 if field == "peakArea" else 1,
                       "columnStep": 3, "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "INDEX" if field == "sequence" else "CELL",
                       "indexBase": 1})
        if field == "sequence":
            config.update({"generateSequence": True, "sequenceDependency": "systemSuitability.peakArea"})
    elif field_code.startswith("specificity."):
        field = field_code.rsplit(".", 1)[-1]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "专属性", "rowStart": 2, "rowEnd": 5,
                       "startColumn": {"solutionName": 2, "retentionTime": 3, "peakArea": 4}.get(field, 1),
                       "columnStep": 0, "rowStep": 5, "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
        if field == "impurityName":
            config.update({"valueMode": "REPEAT_VALUE", "repeatValueSource": {
                "sheet": "专属性", "row": 2, "column": 1, "rowStep": 5, "columnStep": 0,
            }})
    elif field_code in {"uncategorized.field_005", "uncategorized.field_006"}:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "系统适用性", "rowStart": 9, "rowEnd": 9,
                       "startColumn": 2 if field_code.endswith("005") else 3, "columnStep": 3,
                       "rowStep": 0, "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in DETECTION_LIMIT_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "检测限与定量限", "rowStart": 3, "rowEnd": 3,
                       "startColumn": DETECTION_LIMIT_COLUMNS[field_code], "columnStep": 0, "rowStep": 1,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in QUANTITATION_LIMIT_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "检测限与定量限", "rowStart": 8, "rowEnd": 13,
                       "startColumn": QUANTITATION_LIMIT_COLUMNS[field_code], "columnStep": 0, "rowStep": 8,
                       "rowStartOffsetFromRepeatCount": 6, "rowCount": 6,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in LINEARITY_ROWS:
        row = LINEARITY_ROWS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "线性", "rowStart": row, "rowEnd": row,
                       "startColumn": 3, "rowStep": 24, "valueCount": 5,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "HORIZONTAL_CELL"})
    elif field_code in LINEARITY_STATISTICS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "线性", "rowStart": 3, "rowEnd": 3,
                       "xRow": 3, "yRow": 4, "startColumn": 3, "rowStep": 24, "valueCount": 5,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": LINEARITY_STATISTICS[field_code],
                       "broadcastRepeat": True})
    elif field_code == "uncategorized.field_029":
        config.update({"mode": "CHART_IMAGE", "sheet": "线性", "pointsPerTest": 5})
    elif field_code in REPEATABILITY_DETAIL_COLUMNS:
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度", "rowStart": 3, "rowEnd": 8,
                       "startColumn": REPEATABILITY_DETAIL_COLUMNS[field_code], "columnStep": 0, "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    elif field_code in REPEATABILITY_SUMMARY_CELLS:
        row, column = REPEATABILITY_SUMMARY_CELLS[field_code]
        config.update({"mode": "REPEAT_BLOCK", "sheet": "重复性跟中间精密度", "rowStart": row, "rowEnd": row,
                       "startColumn": column, "columnStep": 0, "rowStep": 33,
                       "repeatCountSource": {"sheet": "首页", "row": 8, "column": 2},
                       "maxRepeat": 15, "valueMode": "CELL"})
    return config


# 一次性工作簿布局同步标记：首次启动把存量 Excel 规则/目录/已发布快照对齐到内置布局；
# 之后以管理员的修改为准，启动只做"缺失才播种"，不再回滚配置
EXCEL_LAYOUT_MIGRATION = "2026_excel_rule_defaults_layout_sync_v1"


def ensure_excel_field_rules(database: Any) -> None:
    first_sync = not database.migration_applied(EXCEL_LAYOUT_MIGRATION)
    if first_sync:
        _sync_excel_field_paths(database)
    for field_code, source_path in EXCEL_FIELD_PATHS.items():
        if not database.get_lims_field(field_code):
            continue
        excel_rules = [rule for rule in database.list_system_field_rules(field_code)
                       if rule.get("sourceType") == "EXCEL"]
        existing: list[dict[str, Any]] = []
        for rule in excel_rules:
            config = rule.get("config") if isinstance(rule.get("config"), dict) else {}
            if config.get("sourcePath") != source_path:
                if first_sync:
                    database.delete_system_field_rule(rule["id"])
                continue
            if first_sync:
                expected = _rule_config(field_code, source_path)
                if any(config.get(key) != value for key, value in expected.items()):
                    config = {**config, **expected}
                    database.save_system_field_rule({**rule, "config": config}, rule["id"])
            existing.append(rule)
        if existing:
            continue
        database.save_system_field_rule({
            "fieldCode": field_code, "name": "文霞 V49 验证结果计算页", "sourceType": "EXCEL",
            "priority": 50, "transform": "TRIM", "enabled": True,
            "config": _rule_config(field_code, source_path),
        })
    if first_sync:
        database.mark_migration_applied(EXCEL_LAYOUT_MIGRATION)
