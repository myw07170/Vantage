"""Research subjects must come from LLM recognition and explicit user selection."""
from unittest.mock import Mock

import pytest

from app.core import orchestrator as pipeline


def scope_result(**overrides):
    return {"subject": "Claude Code vs Codex", "domain": "AI coding tools",
            "products": ["Claude Code", "Codex"], "competitors": ["Aider", "Cursor"], **overrides}


@pytest.mark.parametrize("query", [
    "compare Claude Code and Codex", "Claude Code vs Codex", "比较 Claude Code 和 Codex",
])
def test_scoping_passes_original_request_to_llm_and_preserves_complete_products(offline, monkeypatch, query):
    call = Mock(return_value=scope_result(products=[" Claude  Code ", "Codex", "codex", ""],
                                          competitors=["CODEX", "Aider", "aider", "Cursor"]))
    monkeypatch.setattr(pipeline, "chat_json", call)
    scope = pipeline._discover_scope(query)
    assert scope["products"] == ["Claude Code", "Codex"]
    assert scope["competitors"] == ["Aider", "Cursor"]
    messages = call.call_args.args[0]
    assert messages[1] == {"role": "user", "content": query}
    assert call.call_args.kwargs["task_kind"] == "scope"
    question = next(q for q in pipeline._clarify_questions(query, scope) if q["id"] == "products")
    assert question["options"] == ["Claude Code", "Codex", "Aider", "Cursor"]
    assert question["defaultSelected"] == ["Claude Code", "Codex"]


@pytest.mark.parametrize("bad", [None, [], scope_result(products="Claude Code"),
    scope_result(products=[{"name": "Codex"}]), scope_result(products=["Claude Code vs Codex"]),
    scope_result(competitors="Aider"), scope_result(domain=[]), {"subject": "Old-style response"}])
def test_invalid_scope_is_retried_once_without_word_splitting(offline, monkeypatch, bad):
    call = Mock(return_value=bad)
    monkeypatch.setattr(pipeline, "chat_json", call)
    scope = pipeline._discover_scope("compare Claude Code and Codex")
    assert call.call_count == 2
    assert scope["products"] == scope["competitors"] == []
    assert scope["discovery_failed"]
    question = next(q for q in pipeline._clarify_questions("query", scope) if q["id"] == "products")
    assert "failed" in question["hint"]
    assert question["options"] == []


def test_scope_recovers_on_second_response_and_category_only_is_valid(offline, monkeypatch):
    call = Mock(side_effect=[None, scope_result(products=[])])
    monkeypatch.setattr(pipeline, "chat_json", call)
    scope = pipeline._discover_scope("AI coding tools landscape")
    assert call.call_count == 2 and not scope.get("discovery_failed")
    question = next(q for q in pipeline._clarify_questions("query", scope) if q["id"] == "products")
    assert question["defaultSelected"] == []
    assert question["options"] == ["Aider", "Cursor"]


def test_product_names_with_vs_or_compare_are_not_mistaken_for_comparison_topics(offline, monkeypatch):
    call = Mock(return_value=scope_result(products=["VS Code", "Beyond Compare"]))
    monkeypatch.setattr(pipeline, "chat_json", call)
    assert pipeline._discover_scope("compare VS Code and Beyond Compare")["products"] == ["VS Code", "Beyond Compare"]
    assert call.call_count == 1


@pytest.mark.parametrize("selected", [
    ["Codex"], ["Claude Code", "Codex", "Aider"], [f"Product {i}" for i in range(9)],
])
@pytest.mark.parametrize("response", [None, {"subject": "Claude Code vs Codex", "brands": ["Claude", "Code", "Cursor"],
    "focus": ["Pricing"], "search_angles": ["pricing plans"]}])
def test_plan_honors_exact_selection_even_when_llm_adds_products_or_fails(offline, monkeypatch, selected, response):
    monkeypatch.setattr(pipeline, "chat_json", Mock(return_value=response))
    plan = pipeline._plan_research("compare Claude Code and Codex", {
        "_scope": scope_result(), "products": selected, "competitors": ["Unselected legacy rival"],
    })
    assert plan["brands"] == selected


def test_legacy_scope_is_reidentified_and_legacy_competitors_are_additions(offline, monkeypatch):
    discover = Mock(return_value=scope_result())
    monkeypatch.setattr(pipeline, "_discover_scope", discover)
    monkeypatch.setattr(pipeline, "chat_json", Mock(return_value=None))
    result = pipeline._plan_research("compare Claude Code and Codex", {
        "_scope": {"subject": "Claude Code vs OpenAI Codex CLI"}, "competitors": ["Aider"],
    })
    discover.assert_called_once_with("compare Claude Code and Codex")
    assert result["brands"] == ["Claude Code", "Codex", "Aider"]


@pytest.mark.parametrize("products", [[], ["  "], "Codex", [42]])
def test_plan_rejects_empty_or_invalid_confirmed_products(offline, products):
    with pytest.raises(ValueError):
        pipeline._plan_research("compare Claude Code and Codex", {"products": products})
