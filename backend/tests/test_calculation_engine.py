import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from backend.app.database import Database
from backend.app.services.calculation_engine import (
    CalculationError,
    evaluate_formula,
    extract_references,
    validate_calculation,
)
from backend.app.services.mapped_docx_generator import _row_calculated_values
from backend.app.services.rule_admin import RuleAdminRepository


ROOT = Path(__file__).resolve().parents[2]


class CalculationEngineTest(unittest.TestCase):
    def test_arithmetic_rounding_and_recovery_rate(self) -> None:
        result = evaluate_formula(
            "{measured} / {added} * 100",
            ["measured", "added"],
            {"measured": "9.876", "added": "10"},
            precision=2,
        )
        self.assertEqual(result, Decimal("98.76"))

    def test_aggregate_functions_and_rsd(self) -> None:
        values = {"areas": [100, 102, 98]}
        self.assertEqual(
            evaluate_formula("AVG({areas})", ["areas"], values, 2),
            Decimal("100.00"),
        )
        self.assertEqual(
            evaluate_formula("RSD({areas})", ["areas"], values, 2),
            Decimal("2.00"),
        )

    def test_if_can_return_a_conclusion(self) -> None:
        result = evaluate_formula(
            'IF({rsd} <= {limit}, "符合", "不符合")',
            ["rsd", "limit"],
            {"rsd": "1.8", "limit": "2.0"},
        )
        self.assertEqual(result, "符合")

    def test_null_behaviors(self) -> None:
        with self.assertRaises(CalculationError):
            evaluate_formula("SUM({values})", ["values"], {"values": [1, None]}, 2, "ERROR")
        self.assertEqual(
            evaluate_formula("SUM({values})", ["values"], {"values": [1, None]}, 2, "ZERO"),
            Decimal("1.00"),
        )
        self.assertEqual(
            evaluate_formula("AVG({values})", ["values"], {"values": [1, None, 3]}, 2, "SKIP"),
            Decimal("2.00"),
        )

    def test_validation_rejects_unlisted_references_and_unsafe_syntax(self) -> None:
        self.assertEqual(extract_references("{a} + {a} + {b}"), ["a", "b"])
        with self.assertRaises(CalculationError):
            validate_calculation("{a} + {b}", ["a"])
        with self.assertRaises(CalculationError):
            validate_calculation("__import__('os').system('dir')", [])

    def test_current_row_calculation_uses_values_from_the_same_record(self) -> None:
        mappings = [
            {
                "fieldCode": "row.measured", "sourceType": "LIMS",
                "sourcePath": "$.results[*].measured",
            },
            {
                "fieldCode": "row.added", "sourceType": "LIMS",
                "sourcePath": "$.results[*].added",
            },
            {
                "fieldCode": "row.recovery", "sourceType": "CALCULATED",
                "calculationExpression": "{row.measured} / {row.added} * 100",
                "calculationDependencies": ["row.measured", "row.added"],
                "calculationScope": "CURRENT_ROW", "calculationPrecision": 1,
                "calculationNullBehavior": "ERROR",
            },
        ]
        values = _row_calculated_values(
            mappings,
            {"measured": "9.95", "added": "10.0"},
            {},
        )
        self.assertEqual(values["row.recovery"], Decimal("99.5"))


class CalculationDependencyTest(unittest.TestCase):
    def repository(self, directory: str) -> RuleAdminRepository:
        database = Database(Path(directory) / "rules.db")
        database.initialize()
        repository = RuleAdminRepository(database, ROOT / "mapping" / "template-mapping.json")
        repository.seed()
        return repository

    def test_repository_rejects_a_calculation_dependency_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.repository(directory)
            chapter = repository.list_template_chapters()[0]
            block = repository.create_content_block({
                "chapterId": chapter["id"], "title": "计算测试", "kind": "CALCULATED",
                "tableNo": "", "enabled": True,
            })
            common = {
                "chapterId": chapter["id"], "blockId": block["id"],
                "locationId": "", "sectionCode": chapter["code"], "tableNo": "TEXT",
                "dataType": "decimal", "sourceType": "CALCULATED", "sourcePath": "",
                "repeatType": "NONE", "repeatKey": "", "mergeRule": "PRESERVE",
                "fillRule": "TEXT", "calculationRule": "", "controlTag": "",
                "required": False, "sourcePending": False, "enabled": True,
                "calculationScope": "REPORT", "calculationPrecision": 2,
                "calculationNullBehavior": "ERROR",
            }
            repository.create_mapping({
                **common, "wordLabel": "原始值", "fieldCode": "source.value",
                "sourceType": "LIMS", "sourcePath": "$.source.value",
                "calculationExpression": "", "calculationDependencies": [],
            })
            first = repository.create_mapping({
                **common, "wordLabel": "计算一", "fieldCode": "calc.one",
                "calculationExpression": "{source.value} * 2",
                "calculationDependencies": ["source.value"],
            })
            second = repository.create_mapping({
                **common, "wordLabel": "计算二", "fieldCode": "calc.two",
                "calculationExpression": "{calc.one} + 1",
                "calculationDependencies": ["calc.one"],
            })
            with self.assertRaises(ValueError):
                repository.update_mapping(first["id"], {
                    **first,
                    "calculationExpression": "{calc.two} + 1",
                    "calculationDependencies": ["calc.two"],
                })
            self.assertEqual(second["calculationDependencies"], ["calc.one"])


if __name__ == "__main__":
    unittest.main()
