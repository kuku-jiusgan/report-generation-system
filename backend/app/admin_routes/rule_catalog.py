import re
from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.rule_admin import RuleAdminRepository
from ..services.calculation_engine import CalculationError, validate_calculation
from ..services.ai_field_generator import AiGenerationError, generate_ai_text, render_ai_prompt
from ..services.ai_service_config import load_ai_service_config, save_ai_service_config
from ..services.system_field_groups import assign_field_to_group, assign_group_to_chapter, list_system_field_groups, save_system_field_group


CHAPTER_FIELD_PREFIXES = {
    "cover": "cover", "headerFooter": "header", "1": "overview", "2": "purpose",
    "3": "standards", "4": "materials", "5": "summary", "6": "method",
    "7": "validation", "8": "sample_test", "9": "formula", "10": "deviation",
    "11": "attachment", "12": "history",
}


def _field_prefix(repository: RuleAdminRepository, chapter_id: Any) -> str:
    with repository.database.connect() as connection:
        row = connection.execute(
            """WITH RECURSIVE lineage(id,parent_id,code) AS (
               SELECT id,parent_id,code FROM admin_template_chapters WHERE id=?
               UNION ALL SELECT c.id,c.parent_id,c.code FROM admin_template_chapters c
               JOIN lineage l ON l.parent_id=c.id)
               SELECT code FROM lineage WHERE parent_id IS NULL LIMIT 1""", (chapter_id,),
        ).fetchone() if chapter_id else None
    return (CHAPTER_FIELD_PREFIXES.get(str(row["code"])) if row else None) or "uncategorized"


def _validate_standard_field(
    repository: RuleAdminRepository, item: dict[str, Any], original_code: str = "",
) -> dict[str, Any]:
    field_code = str(item.get("fieldCode") or "").strip()
    if not field_code and not original_code:
        prefix = _field_prefix(repository, item.get("chapterId"))
        with repository.database.connect() as connection:
            rows = connection.execute(
                "SELECT field_code FROM lims_field_catalog WHERE field_code LIKE ?", (f"{prefix}.field_%",),
            ).fetchall()
        numbers = [int(match.group(1)) for row in rows
                   if (match := re.fullmatch(rf"{re.escape(prefix)}\.field_(\d+)", str(row["field_code"]))) is not None]
        field_code = f"{prefix}.field_{max(numbers, default=0) + 1:03d}"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", field_code):
        raise HTTPException(422, "标准字段编码只能使用英文字母、数字、点和下划线，且必须以字母开头")
    if not str(item.get("label") or "").strip():
        raise HTTPException(422, "标准字段名称不能为空")
    if item.get("validationRegex"):
        try:
            re.compile(str(item["validationRegex"]))
        except re.error as error:
            raise HTTPException(422, f"校验正则无效：{error}") from error
    existing = repository.database.get_lims_field(field_code)
    if existing and field_code != original_code:
        raise HTTPException(409, "标准字段编码已存在")
    defaults = {
        "groupCode": "未分类", "collectionCode": "custom", "dataType": "string",
        "cardinality": "ONE", "dbTable": "system_generated_fields", "dbColumn": "value_json",
        "jsonKey": field_code.rsplit(".", 1)[-1], "legacyJsonPath": f"$.custom.{field_code.rsplit('.', 1)[-1]}",
        "description": "", "outputFormat": "", "defaultValue": "", "validationRegex": "",
        "orderNo": 0, "enabled": True,
    }
    return {**defaults, **item, "fieldCode": field_code, "label": str(item["label"]).strip()}


def _validate_system_rule(repository: RuleAdminRepository, item: dict[str, Any]) -> dict[str, Any]:
    field_code = str(item.get("fieldCode") or "")
    if not repository.database.get_lims_field(field_code):
        raise HTTPException(422, "系统字段不存在")
    if not str(item.get("name") or "").strip():
        raise HTTPException(422, "规则名称不能为空")
    source_type = str(item.get("sourceType") or "LIMS").upper()
    if source_type not in {"LIMS", "AI", "EXCEL", "PDF", "CALCULATED"}:
        raise HTTPException(422, f"不支持的系统字段来源：{source_type}")
    config = item.get("config") if isinstance(item.get("config"), dict) else {}
    for key in ("sectionPattern", "headerPattern", "valuePattern", "rowPattern"):
        pattern = config.get(key)
        if pattern:
            try:
                re.compile(str(pattern))
            except re.error as error:
                raise HTTPException(422, f"{key} 正则无效：{error}") from error
    if source_type == "CALCULATED":
        dependencies = [str(value) for value in config.get("dependencies", [])]
        known = {field["fieldCode"] for field in repository.database.list_lims_fields(True)}
        missing = [value for value in dependencies if value not in known]
        if missing:
            raise HTTPException(422, f"依赖的系统字段不存在：{', '.join(missing)}")
        if field_code in dependencies:
            raise HTTPException(422, "计算或拼接规则不能依赖自身")
        if not str(config.get("textTemplate") or "").strip():
            try:
                validate_calculation(str(config.get("expression") or ""), dependencies)
            except CalculationError as error:
                raise HTTPException(422, str(error)) from error
        graph = {
            str(rule["fieldCode"]): [str(value) for value in rule.get("config", {}).get("dependencies", [])]
            for rule in repository.database.list_system_field_rules()
            if rule.get("sourceType") == "CALCULATED"
        }
        graph[field_code] = dependencies
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(code: str) -> None:
            if code in visiting:
                raise HTTPException(422, "计算或拼接规则存在循环依赖")
            if code in visited or code not in graph:
                return
            visiting.add(code)
            for dependency in graph[code]:
                visit(dependency)
            visiting.remove(code)
            visited.add(code)

        visit(field_code)
    if source_type == "AI":
        known = {field["fieldCode"] for field in repository.database.list_lims_fields(True)}
        variables = config.get("contextVariables") or [
            {"fieldCode": value} for value in config.get("inputFields", [])
        ]
        missing = [str(item.get("fieldCode")) for item in variables
                   if isinstance(item, dict) and item.get("fieldCode") not in known]
        if missing:
            raise HTTPException(422, f"AI 上下文字段不存在：{', '.join(missing)}")
        prompt = str(config.get("promptTemplate") or "")
        unknown = [name for name in re.findall(r"\{\{([^{}]+)\}\}", prompt)
                   if name.strip() not in {str(item.get("fieldCode")) for item in variables if isinstance(item, dict)}]
        if unknown:
            raise HTTPException(422, f"AI 提示词引用了未配置的字段：{', '.join(unknown)}")
    return {**item, "fieldCode": field_code, "sourceType": source_type, "config": config}


def _resolve_standard_field(repository: RuleAdminRepository, item: dict[str, Any]) -> None:
    code = str(item.get("standardFieldCode") or "")
    if not code:
        return
    field = next(
        (value for value in repository.database.list_lims_fields() if value["fieldCode"] == code),
        None,
    )
    if not field:
        raise HTTPException(422, "标准字段不存在或已停用")
    item["sourcePath"] = field["legacyJsonPath"]
    item["dataType"] = field["dataType"]
    item["sourceType"] = "SYSTEM"
    item["calculationExpression"] = ""
    item["calculationDependencies"] = []


def register_rule_catalog_routes(router: APIRouter, repository: RuleAdminRepository) -> None:
    @router.get("/ai-service-config")
    def get_ai_service_config() -> dict[str, Any]:
        return load_ai_service_config(False)

    @router.put("/ai-service-config")
    def update_ai_service_config(item: dict[str, Any]) -> dict[str, Any]:
        if not str(item.get("baseUrl") or "").strip():
            raise HTTPException(422, "AI 接口地址不能为空")
        if not str(item.get("model") or "").strip():
            raise HTTPException(422, "AI 模型不能为空")
        return save_ai_service_config(item)

    @router.post("/ai-service-config/test")
    def test_ai_service_config() -> dict[str, Any]:
        try:
            output = generate_ai_text("connection.test", {
                "id": "connection-test", "config": {
                    "promptTemplate": "请只回复：连接成功", "contextVariables": [],
                    "maxLength": 30, "temperature": 0,
                },
            }, {})
            return {"success": True, "output": output}
        except AiGenerationError as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/mappings")
    def list_mappings(search: str = "", table_no: str = "", source_type: str = "") -> list[dict[str, Any]]:
        return repository.list_mappings(search, table_no, source_type)

    @router.get("/field-groups")
    def field_groups() -> list[dict[str, Any]]:
        return list_system_field_groups(repository.database)

    @router.post("/field-groups")
    def create_field_group(item: dict[str, Any]) -> dict[str, Any]:
        try:
            return save_system_field_group(repository.database, item)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.put("/field-groups/{group_code}")
    def update_field_group(group_code: str, item: dict[str, Any]) -> dict[str, Any]:
        try:
            return save_system_field_group(repository.database, {**item, "groupCode": group_code}, group_code)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.post("/field-groups/{group_code}/fields")
    def assign_group_field(group_code: str, item: dict[str, Any]) -> dict[str, Any]:
        try:
            return assign_field_to_group(repository.database, group_code, str(item.get("fieldCode") or ""), str(item.get("fieldPath") or ""))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.post("/field-groups/{group_code}/chapters")
    def assign_group_chapter(group_code: str, item: dict[str, Any]) -> dict[str, Any]:
        try:
            return assign_group_to_chapter(repository.database, group_code, int(item.get("chapterId")))
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/standard-fields")
    def list_standard_fields(include_disabled: bool = False, chapter_id: int | None = None) -> list[dict[str, Any]]:
        if chapter_id is not None and not include_disabled:
            return repository.database.list_lims_fields_for_chapter(chapter_id)
        return repository.database.list_lims_fields(include_disabled)

    @router.get("/standard-field-catalog")
    def standard_field_catalog(include_disabled: bool = True) -> dict[str, Any]:
        return repository.standard_field_catalog(include_disabled)

    @router.post("/standard-fields")
    def create_standard_field(item: dict[str, Any]) -> dict[str, Any]:
        validated = _validate_standard_field(repository, item)
        saved = repository.database.upsert_lims_field(validated)
        if item.get("chapterId"):
            with repository.database.connect() as connection:
                connection.execute(
                    """INSERT OR IGNORE INTO system_field_chapters(field_code,chapter_id,order_no)
                       VALUES(?,?,?)""", (saved["fieldCode"], item["chapterId"], saved.get("orderNo", 0)),
                )
        if item.get("groupCode"):
            assign_field_to_group(repository.database, str(item["groupCode"]), saved["fieldCode"])
        return saved

    @router.put("/standard-fields/{field_code:path}")
    def update_standard_field(field_code: str, item: dict[str, Any]) -> dict[str, Any]:
        existing = repository.database.get_lims_field(field_code)
        if not existing:
            raise HTTPException(404, "标准字段不存在")
        updated = _validate_standard_field(repository, {**existing, **item}, field_code)
        if updated["fieldCode"] != field_code:
            raise HTTPException(422, "字段编码创建后不能修改；请新建字段并迁移模板引用")
        return repository.database.upsert_lims_field(updated)

    @router.delete("/standard-fields/{field_code:path}")
    def delete_standard_field(field_code: str) -> dict[str, bool]:
        with repository.database.connect() as connection:
            used = connection.execute(
                "SELECT COUNT(*) FROM admin_mapping_rules WHERE standard_field_code=?", (field_code,),
            ).fetchone()[0]
        if used:
            raise HTTPException(409, f"该标准字段正被 {used} 个模板字段引用，请先停用或迁移引用")
        if not repository.database.delete_lims_field(field_code):
            raise HTTPException(404, "标准字段不存在")
        return {"deleted": True}

    @router.get("/standard-fields/{field_code:path}/preview")
    def preview_standard_field(field_code: str, limit: int = 12, instance_ids: str = "") -> dict[str, Any]:
        field = repository.database.get_lims_field(field_code)
        if not field:
            raise HTTPException(404, "标准字段不存在")
        selected = [value.strip() for value in instance_ids.split(",") if value.strip()]
        return repository.database.preview_lims_field(field, limit, selected)

    @router.get("/standard-field-source")
    def standard_field_source(
        field_code: str, import_id: str, instance_id: str, record_key: str = "",
    ) -> dict[str, Any]:
        del record_key
        field = repository.database.get_lims_field(field_code)
        if not field:
            raise HTTPException(404, "标准字段不存在")
        result = repository.database.get_lims_field_instance_source(field, import_id, instance_id)
        if not result:
            raise HTTPException(404, "LIMS 实验实例不存在")
        return result

    @router.get("/system-fields/{field_code:path}/rules")
    def list_system_field_rules(field_code: str) -> list[dict[str, Any]]:
        if not repository.database.get_lims_field(field_code):
            raise HTTPException(404, "系统字段不存在")
        return repository.database.list_system_field_rules(field_code)

    @router.post("/system-fields/{field_code:path}/rules")
    def create_system_field_rule(field_code: str, item: dict[str, Any]) -> dict[str, Any]:
        return repository.database.save_system_field_rule(
            _validate_system_rule(repository, {**item, "fieldCode": field_code}),
        )

    @router.put("/system-field-rules/{rule_id}")
    def update_system_field_rule(rule_id: int, item: dict[str, Any]) -> dict[str, Any]:
        try:
            return repository.database.save_system_field_rule(
                _validate_system_rule(repository, item), rule_id,
            )
        except KeyError as error:
            raise HTTPException(404, "系统字段规则不存在") from error

    @router.delete("/system-field-rules/{rule_id}")
    def delete_system_field_rule(rule_id: int) -> dict[str, bool]:
        if not repository.database.delete_system_field_rule(rule_id):
            raise HTTPException(404, "系统字段规则不存在")
        return {"deleted": True}

    @router.post("/system-field-rules/ai-preview")
    def preview_ai_rule(item: dict[str, Any]) -> dict[str, Any]:
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
        values = item.get("values") if isinstance(item.get("values"), dict) else {}
        try:
            prompt, context = render_ai_prompt(config, values)
            output = generate_ai_text(
                str(item.get("fieldCode") or "preview"),
                {"id": item.get("ruleId"), "config": config}, values,
            ) if item.get("execute") else ""
            return {"success": True, "prompt": prompt, "context": context, "output": output}
        except AiGenerationError as error:
            raise HTTPException(422, str(error)) from error

    @router.post("/mappings")
    def create_mapping(item: dict[str, Any]) -> dict[str, Any]:
        try:
            _resolve_standard_field(repository, item)
            result = repository.create_mapping(item)
            repository.save_active_workspace()
            return result
        except Exception as error:
            raise HTTPException(400, f"创建映射失败：{error}") from error

    @router.put("/mappings/{rule_id}")
    def update_mapping(rule_id: int, item: dict[str, Any]) -> dict[str, Any]:
        _resolve_standard_field(repository, item)
        result = repository.update_mapping(rule_id, item)
        if not result:
            raise HTTPException(404, "映射规则不存在")
        repository.save_active_workspace()
        return result

    @router.delete("/mappings/{rule_id}")
    def delete_mapping(rule_id: int) -> dict[str, bool]:
        if not repository.delete_mapping(rule_id):
            raise HTTPException(404, "映射规则不存在")
        repository.save_active_workspace()
        return {"deleted": True}

    @router.get("/table-rules")
    def list_table_rules() -> list[dict[str, Any]]:
        return repository.list_table_rules()

    @router.put("/table-rules/{table_no}")
    def update_table_rule(table_no: str, item: dict[str, Any]) -> dict[str, Any]:
        item["tableNo"] = table_no.upper()
        result = repository.upsert_table_rule(item)
        repository.save_active_workspace()
        return result
