import threading

from backend.app.services import system_field_resolver


def _field(code: str, path: str, collection: str = "") -> dict:
    return {
        "fieldCode": code, "legacyJsonPath": path, "collectionCode": collection,
        "enabled": True,
    }


def _rule(code: str, config: dict, rule_id: int) -> dict:
    return {
        "id": rule_id, "fieldCode": code, "name": f"AI-{code}", "sourceType": "AI",
        "priority": 1, "config": config, "enabled": True,
    }


def test_independent_ai_fields_run_concurrently(monkeypatch) -> None:
    barrier = threading.Barrier(2)

    def generate(code, rule, values, current_record=None, context_fields=None):
        barrier.wait(timeout=2)
        return f"生成-{code}"

    monkeypatch.setattr(system_field_resolver, "generate_ai_text", generate)
    fields = [_field("first", "$.first"), _field("second", "$.second")]
    rules = [
        _rule("first", {"promptTemplate": "生成第一个字段"}, 1),
        _rule("second", {"promptTemplate": "生成第二个字段"}, 2),
    ]
    payload: dict = {}

    system_field_resolver.resolve_system_fields(fields, rules, payload, {})

    assert payload == {"first": "生成-first", "second": "生成-second"}


def test_current_record_ai_calls_run_concurrently_and_keep_order(monkeypatch) -> None:
    records = [{"name": name} for name in ("甲", "乙", "丙", "丁")]
    barrier = threading.Barrier(len(records))

    def generate(code, rule, values, current_record=None, context_fields=None):
        barrier.wait(timeout=2)
        return f"结论-{current_record['name']}"

    monkeypatch.setattr(system_field_resolver, "generate_ai_text", generate)
    fields = [_field("items.conclusion", "$.items[*].conclusion", "items")]
    rules = [_rule("items.conclusion", {
        "contextVariables": [{"groupCode": "items", "mode": "CURRENT_RECORD"}],
        "promptTemplate": "{{items}}",
    }, 1)]
    payload = {"items": records}

    system_field_resolver.resolve_system_fields(fields, rules, payload, {})

    assert [record["conclusion"] for record in payload["items"]] == [
        "结论-甲", "结论-乙", "结论-丙", "结论-丁",
    ]


def test_ai_dependency_runs_in_next_batch(monkeypatch) -> None:
    calls: list[str] = []

    def generate(code, rule, values, current_record=None, context_fields=None):
        calls.append(code)
        if code == "summary":
            assert values["draft"] == "草稿内容"
        return "最终摘要" if code == "summary" else "草稿内容"

    monkeypatch.setattr(system_field_resolver, "generate_ai_text", generate)
    fields = [_field("summary", "$.summary"), _field("draft", "$.draft")]
    rules = [
        _rule("summary", {
            "contextVariables": [{"fieldCode": "draft", "required": True}],
            "promptTemplate": "总结：{{draft}}",
        }, 1),
        _rule("draft", {"promptTemplate": "生成草稿"}, 2),
    ]
    payload: dict = {}

    system_field_resolver.resolve_system_fields(fields, rules, payload, {})

    assert calls == ["draft", "summary"]
    assert payload == {"draft": "草稿内容", "summary": "最终摘要"}


def test_ai_executor_uses_provider_concurrency_limit() -> None:
    assert system_field_resolver.AI_MAX_CONCURRENCY == 200
    assert system_field_resolver._AI_EXECUTOR._max_workers == 200
