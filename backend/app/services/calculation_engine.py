import ast
import math
import operator
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from statistics import stdev
from typing import Any


REFERENCE_PATTERN = re.compile(r"\{([^{}]+)\}")


class CalculationError(ValueError):
    pass


def extract_references(expression: str) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in REFERENCE_PATTERN.findall(expression) if value.strip()))


def _compile_expression(expression: str, dependencies: list[str]) -> tuple[ast.Expression, dict[str, str]]:
    if not expression.strip():
        raise CalculationError("计算公式不能为空")
    references = extract_references(expression)
    missing = [value for value in references if value not in dependencies]
    if missing:
        raise CalculationError(f"公式引用未加入依赖字段：{', '.join(missing)}")
    aliases = {code: f"_field_{index}" for index, code in enumerate(references)}
    compiled = expression
    for code in sorted(aliases, key=len, reverse=True):
        compiled = compiled.replace(f"{{{code}}}", aliases[code])
    try:
        tree = ast.parse(compiled, mode="eval")
    except SyntaxError as error:
        raise CalculationError(f"公式语法错误：{error.msg}") from error
    allowed = (
        ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
        ast.BoolOp, ast.Compare, ast.Call, ast.Add, ast.Sub, ast.Mult, ast.Div,
        ast.Pow, ast.Mod, ast.USub, ast.UAdd, ast.And, ast.Or, ast.Eq, ast.NotEq,
        ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise CalculationError(f"公式包含不支持的语法：{type(node).__name__}")
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise CalculationError("公式函数格式不正确")
    return tree, aliases


def validate_calculation(expression: str, dependencies: list[str]) -> list[str]:
    _compile_expression(expression, dependencies)
    return extract_references(expression)


def _decimal(value: Any, null_behavior: str) -> Decimal | None:
    if value in (None, ""):
        if null_behavior == "ZERO":
            return Decimal(0)
        if null_behavior == "SKIP":
            return None
        raise CalculationError("依赖字段存在空值")
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as error:
        raise CalculationError(f"无法将“{value}”作为数值计算") from error


def _numbers(values: list[Any], null_behavior: str) -> list[Decimal]:
    flattened: list[Any] = []
    for value in values:
        flattened.extend(value if isinstance(value, list) else [value])
    result = [_decimal(value, null_behavior) for value in flattened]
    return [value for value in result if value is not None]


def evaluate_formula(
    expression: str,
    dependencies: list[str],
    values: dict[str, Any],
    precision: int = 2,
    null_behavior: str = "ERROR",
) -> Any:
    tree, aliases = _compile_expression(expression, dependencies)
    environment = {alias: values.get(code) for code, alias in aliases.items()}
    binary = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    }
    comparisons = {
        ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    }

    def evaluate(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return Decimal(str(node.value))
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in environment:
                raise CalculationError(f"未知字段或函数：{node.id}")
            value = environment[node.id]
            if isinstance(value, list):
                return value
            number = _decimal(value, null_behavior)
            return number
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if left is None or right is None:
                return None
            try:
                return binary[type(node.op)](left, right)
            except (ArithmeticError, TypeError, ValueError, KeyError) as error:
                raise CalculationError(f"公式运算失败：{error}") from error
        if isinstance(node, ast.UnaryOp):
            value = evaluate(node.operand)
            if value is None:
                raise CalculationError("一元运算依赖了空值字段")
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BoolOp):
            values_ = [bool(evaluate(value)) for value in node.values]
            return all(values_) if isinstance(node.op, ast.And) else any(values_)
        if isinstance(node, ast.Compare):
            left = evaluate(node.left)
            for operation, comparator in zip(node.ops, node.comparators):
                right = evaluate(comparator)
                if left is None or right is None:
                    raise CalculationError("比较运算依赖了空值字段")
                try:
                    matched = comparisons[type(operation)](left, right)
                except TypeError as error:
                    raise CalculationError(f"比较运算失败：{error}") from error
                if not matched:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            name = node.func.id.upper()
            if name == "IF":
                if len(node.args) != 3:
                    raise CalculationError("IF 函数需要条件、成立值和不成立值三个参数")
                return evaluate(node.args[1]) if bool(evaluate(node.args[0])) else evaluate(node.args[2])
            arguments = [evaluate(argument) for argument in node.args]
            numbers = _numbers(arguments, null_behavior)
            if name == "SUM":
                return sum(numbers, Decimal(0))
            if name == "AVG":
                if not numbers:
                    raise CalculationError("AVG 没有可计算的数值")
                return sum(numbers, Decimal(0)) / Decimal(len(numbers))
            if name == "MIN":
                if not numbers:
                    raise CalculationError("MIN 没有可计算的数值")
                return min(numbers)
            if name == "MAX":
                if not numbers:
                    raise CalculationError("MAX 没有可计算的数值")
                return max(numbers)
            if name == "COUNT":
                return Decimal(len(numbers))
            if name == "ABS":
                if len(numbers) != 1:
                    raise CalculationError("ABS 需要一个数值")
                return abs(numbers[0])
            if name == "RSD":
                if len(numbers) < 2:
                    raise CalculationError("RSD 至少需要两个数值")
                mean = sum(numbers, Decimal(0)) / Decimal(len(numbers))
                if mean == 0:
                    raise CalculationError("RSD 的平均值不能为 0")
                deviation = Decimal(str(stdev(float(value) for value in numbers)))
                return deviation / mean * Decimal(100)
            if name == "SQRT":
                if len(numbers) != 1 or numbers[0] < 0:
                    raise CalculationError("SQRT 需要一个非负数值")
                return Decimal(str(math.sqrt(float(numbers[0]))))
            raise CalculationError(f"不支持的函数：{name}")
        raise CalculationError(f"不支持的公式节点：{type(node).__name__}")

    result = evaluate(tree)
    if isinstance(result, Decimal):
        quantum = Decimal(1).scaleb(-max(0, min(int(precision), 12)))
        result = result.quantize(quantum, rounding=ROUND_HALF_UP)
    return result
