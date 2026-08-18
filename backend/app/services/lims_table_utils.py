import re
from typing import Any

from lxml import html


def clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def cell_value(cell: html.HtmlElement) -> str:
    text = clean_cell(cell.text_content())
    if text:
        return text
    image_urls = [str(value).strip() for value in cell.xpath(".//img/@src") if str(value).strip()]
    return "；".join(dict.fromkeys(image_urls))


def column_value(row: list[str], column: int | None) -> str:
    return clean_cell(row[column]) if column is not None and column < len(row) else ""


def _semantic(value: Any) -> str:
    return re.sub(r"[\s\u3000]+", "", clean_cell(value)).replace("（", "(").replace("）", ")")


def _header_index(headers: list[str], *patterns: str) -> int | None:
    for index, header in enumerate(headers):
        if any(re.fullmatch(pattern, _semantic(header), re.IGNORECASE) for pattern in patterns):
            return index
    return None


def impurity_columns(headers: list[str]) -> dict[str, int | None] | None:
    columns = {
        "name": _header_index(headers, r"(?:杂质)?名称", r"化合物名称"),
        "cas": _header_index(headers, r"CAS(?:号|编号|No\.?)?"),
        "structure": _header_index(headers, r"(?:化学)?结构式?", r"结构图片"),
        "limit": _header_index(headers, r"(?:杂质)?限度(?:\([^)]*\))?", r"限量(?:\([^)]*\))?"),
    }
    required = (columns["name"], columns["cas"], columns["limit"])
    return columns if all(value is not None for value in required) else None


def validation_summary_columns(headers: list[str]) -> dict[str, int] | None:
    project = _header_index(headers, r"(?:验证|试验|检验)?项目", r"验证内容", r"项目名称")
    criteria = _header_index(
        headers, r"(?:可)?接受标准", r"接收标准", r"验收标准", r"判定标准", r"AcceptanceCriteria",
    )
    if project is None or criteria is None:
        return None
    return {"project": project, "criteria": criteria}


def limit_calculation_records(rows: list[list[str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    patterns = {
        "impurityName": (r"(?:杂质)?名称",), "field2": (r"AI值(?:\([^)]*\))?", r"每日允许摄入量.*"),
        "field3": (r"最大日剂量(?:\([^)]*\))?",), "field4": (r"杂质限度(?:\([^)]*\))?",),
        "field5": (r"供试品溶液中API浓度(?:\([^)]*\))?", r"API浓度(?:\([^)]*\))?"),
        "field6": (r"杂质限度浓度(?:\([^)]*\))?", r"限度浓度(?:\([^)]*\))?"),
    }
    columns = {key: _header_index(rows[0], *aliases) for key, aliases in patterns.items()}
    if any(column is None for column in columns.values()):
        return []
    return [
        {key: clean_cell(row[column]) if column is not None and column < len(row) else ""
         for key, column in columns.items()}
        for row in rows[1:] if any(clean_cell(cell) for cell in row)
    ]
