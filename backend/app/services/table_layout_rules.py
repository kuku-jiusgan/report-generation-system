"""表格布局规则的只读视图。

模板编译和报告生成都需要知道"某张语义表在 Word 里是第几张表""按行重复还是
按矩阵填充""哪些汇总行不能删""表里的图片要不要清掉""矩阵表的行列版式是什么"。
这些以前是后端模块常量，设计器看不到；现在统一来自 admin_table_rules，
本模块只负责把配置读成生成器好用的形状，不提供任何内置默认值——
配置缺失时返回空值并由调用方给出可见警告，而不是猜一个规则继续跑。
"""

import hashlib
import json
import re
from typing import Any


# Word 书签名最长 40 个字符，且只接受字母、数字和下划线。
BOOKMARK_NAME_LIMIT = 40


def repeat_bookmark_name(table_no: str) -> str:
    """语义表号 → 原型行书签名。

    表号可能是 `T13`，也可能是设计器按标准编组生成的 `GROUP:systemSuitability`；
    冒号一类字符不能出现在 Word 书签名里，这里统一转成下划线。编译和填充必须
    用同一个函数，否则填充时找不到编译阶段埋下的书签。
    """
    safe = re.sub(r"\W+", "_", str(table_no).lower(), flags=re.UNICODE).strip("_")
    budget = BOOKMARK_NAME_LIMIT - len("repeat__row")
    if len(safe) > budget:
        digest = hashlib.sha256(str(table_no).encode("utf-8")).hexdigest()[:4]
        safe = f"{safe[:budget - 5]}_{digest}"
    return f"repeat_{safe}_row"


class TableLayoutRules:
    def __init__(self, table_rules: list[dict[str, Any]] | None = None) -> None:
        self._rules = {str(item.get("tableNo") or ""): item for item in (table_rules or [])}

    def rule(self, table_no: str) -> dict[str, Any]:
        return self._rules.get(str(table_no), {})

    def physical_index(self, table_no: str) -> int:
        """语义表号对应的 Word 正文表格序号；0 表示设计器里没有配置。"""
        return int(self.rule(table_no).get("physicalTableIndex") or 0)

    @staticmethod
    def anchored_index(document: Any, table_no: str, mappings: list[dict[str, Any]]) -> int:
        explicit = 0
        try:
            explicit = int(next((item for item in mappings if item.get("tableNo") == table_no), {}).get("physicalTableIndex") or 0)
        except (TypeError, ValueError):
            explicit = 0
        if explicit > 0:
            return explicit
        tags = [str(item.get("controlTag") or "") for item in mappings
                if item.get("tableNo") == table_no and item.get("controlTag")]
        tables = document.xpath(".//w:tbl", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"})
        for index, table in enumerate(tables, start=1):
            if any(table.xpath(".//w:sdt[w:sdtPr/w:tag/@w:val=$tag]", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}, tag=tag) for tag in tags):
                return index
        return 0

    def preserved_row_labels(self, table_no: str) -> tuple[str, ...]:
        labels = self.rule(table_no).get("preservedRowLabels") or []
        return tuple(str(label) for label in labels if str(label).strip())

    def clears_embedded_objects(self, table_no: str) -> bool:
        return bool(self.rule(table_no).get("clearEmbeddedObjects"))

    def is_matrix(self, table_no: str) -> bool:
        return str(self.rule(table_no).get("mode") or "") == "MATRIX"

    def is_table_repeat(self, table_no: str) -> bool:
        return str(self.rule(table_no).get("mode") or "") == "TABLE_REPEAT"

    def data_row_start(self, table_no: str) -> int:
        """原型数据行在 Word 表格里的行号；0 表示没配，退回书签定位。"""
        try:
            return max(0, int(self.rule(table_no).get("dataRowStart") or 0))
        except (TypeError, ValueError):
            return 0

    def group_field(self, table_no: str) -> str:
        """横向分组字段（记录里的键）；空表示这张表只向下填充，不向右扩列。"""
        return str((self.matrix_layout(table_no) or {}).get("groupField") or "").strip()

    def equal_group_columns(self, table_no: str) -> bool:
        """多个分组时子列等宽；否则按 Word 原型的列宽比例缩放。"""
        return str((self.matrix_layout(table_no) or {}).get("groupColumnWidth") or "") == "EQUAL"

    def matrix_layout(self, table_no: str) -> dict[str, Any] | None:
        """矩阵版式配置；未配置或 JSON 非法时返回 None，由调用方警告。"""
        raw = self.rule(table_no).get("matrixLayout") or ""
        if isinstance(raw, dict):
            return raw or None
        text = str(raw).strip()
        if not text:
            return None
        try:
            layout = json.loads(text)
        except json.JSONDecodeError:
            return None
        return layout if isinstance(layout, dict) else None

    def object_clearing_tables(self) -> list[str]:
        return [table_no for table_no, item in self._rules.items()
                if item.get("clearEmbeddedObjects") and item.get("enabled", True)]
