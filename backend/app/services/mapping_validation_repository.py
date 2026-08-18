import re
import unicodedata
from typing import Any

from .calculation_engine import validate_calculation


class MappingValidationRepositoryMixin:
    """Identifier normalization and calculated-field dependency validation."""

    @staticmethod
    def _identifier_segment(value: Any, fallback: str, max_length: int = 48) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
        normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")
        return (normalized or fallback)[:max_length]

    @staticmethod
    def _is_temporary_identifier(value: Any) -> bool:
        current = str(value or "").strip()
        return (
            not current or current.isdigit() or current.startswith("draft.")
            or re.fullmatch(r"(?:word\.)?contentcontrol\.\d+", current, re.IGNORECASE) is not None
            or re.fullmatch(r"report\..+\.mapping\.\d+", current) is not None
        )

    def ensure_mapping_identifiers(self, item: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        result = dict(item)
        with self.database.connect() as connection:
            existing = self._existing_mapping(connection, rule_id)
            chapter_id = self._related_id(connection, "admin_mapping_chapters", "chapter_id", result, rule_id)
            chapter = connection.execute(
                "SELECT code,title FROM admin_template_chapters WHERE id=?", (chapter_id,),
            ).fetchone() if chapter_id else None
            block_id = self._related_id(connection, "admin_mapping_blocks", "block_id", result, rule_id)
            block = connection.execute(
                "SELECT title FROM admin_content_blocks WHERE id=?", (block_id,),
            ).fetchone() if block_id else None
            label = str(result.get("wordLabel") or (existing or {}).get("word_label") or "").strip()
            result["wordLabel"] = label or (f"{block['title']}字段" if block else "未命名字段")
            generated_code = self._generated_field_code(result, existing, chapter, block, rule_id)
            current_code = result.get("fieldCode", (existing or {}).get("field_code", ""))
            field_code = generated_code if self._is_temporary_identifier(current_code) else str(current_code)
            duplicate = connection.execute(
                "SELECT id FROM admin_mapping_rules WHERE field_code=? AND (? IS NULL OR id<>?) LIMIT 1",
                (field_code, rule_id, rule_id),
            ).fetchone()
            result["fieldCode"] = f"{generated_code}.m{rule_id or duplicate['id'] + 1}" if duplicate else field_code
            current_tag = result.get("controlTag", (existing or {}).get("control_tag", ""))
            result["controlTag"] = f"cc.{result['fieldCode']}" if self._is_temporary_identifier(current_tag) else str(current_tag)
            result["locationId"] = self._unique_location(connection, result, existing, rule_id)
        return result

    @staticmethod
    def _existing_mapping(connection: Any, rule_id: int | None) -> dict[str, Any] | None:
        if rule_id is None:
            return None
        row = connection.execute("SELECT * FROM admin_mapping_rules WHERE id=?", (rule_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _related_id(
        connection: Any, table: str, column: str, item: dict[str, Any], rule_id: int | None,
    ) -> Any:
        api_key = "chapterId" if column == "chapter_id" else "blockId"
        if item.get(api_key) or rule_id is None:
            return item.get(api_key)
        row = connection.execute(f"SELECT {column} FROM {table} WHERE mapping_id=?", (rule_id,)).fetchone()
        return row[0] if row else None

    def _generated_field_code(
        self, result: dict[str, Any], existing: dict[str, Any] | None,
        chapter: Any, block: Any, rule_id: int | None,
    ) -> str:
        raw_section = str(result.get("sectionCode") or (existing or {}).get("section_code")
                          or (chapter["code"] if chapter else "field"))
        section = self._identifier_segment(raw_section, "field")
        if raw_section not in {"cover", "headerFooter"}:
            section = f"s{section}"
        field = self._identifier_segment(result["wordLabel"], f"field_{rule_id or 'new'}")
        block_name = self._identifier_segment(block["title"], "") if block else ""
        parts = ["report", section]
        if block_name and block_name != field:
            parts.append(block_name)
        return ".".join([*parts, field])

    def _unique_location(
        self, connection: Any, result: dict[str, Any], existing: dict[str, Any] | None, rule_id: int | None,
    ) -> str:
        current = result.get("locationId", (existing or {}).get("location_id", ""))
        if self._is_temporary_identifier(current) or not current:
            current = f"word.content_control.{result['controlTag']}"
        duplicate = connection.execute(
            "SELECT id FROM admin_mapping_rules WHERE location_id=? AND (? IS NULL OR id<>?) LIMIT 1",
            (current, rule_id, rule_id),
        ).fetchone()
        if duplicate:
            current = f"word.content_control.{result['controlTag']}.m{rule_id or duplicate['id'] + 1}"
        return str(current)

    def validate_calculation_mapping(self, item: dict[str, Any], rule_id: int | None = None) -> None:
        if item.get("sourceType") != "CALCULATED":
            return
        expression = str(item.get("calculationExpression") or "").strip()
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
            for mapping in mappings if mapping.get("sourceType") == "CALCULATED" and mapping["id"] != rule_id
        }
        graph[field_code] = dependencies
        self._validate_dependency_graph(graph, field_code, set(), set())

    @classmethod
    def _validate_dependency_graph(
        cls, graph: dict[str, list[str]], code: str, visiting: set[str], visited: set[str],
    ) -> None:
        if code in visiting:
            raise ValueError("计算字段存在循环依赖")
        if code in visited or code not in graph:
            return
        visiting.add(code)
        for dependency in graph[code]:
            cls._validate_dependency_graph(graph, dependency, visiting, visited)
        visiting.remove(code)
        visited.add(code)
