"""User-visible scope summaries must not expose the model's internal context."""
import json

import pytest

from app.core import db, orchestrator as pipeline


@pytest.mark.parametrize("products, expected", [
    (["Codex"], "Preparing Quick research on Codex."),
    (["Claude Code", "Codex"], "Preparing Quick research on Claude Code and Codex."),
    (["Notion", "Obsidian", "Craft"], "Preparing Quick research on Notion, Obsidian, and Craft."),
])
def test_summary_preserves_complete_confirmed_product_names(products, expected):
    clar = {"products": products, "_resolved_brief": "A rejected interpretation involving Another Tool"}
    text = pipeline._intake_summary(products, clar, "Quick")
    assert text == expected + " Market: United States."
    assert "Another Tool" not in text


def test_summary_shows_confirmed_goal_and_only_three_priorities():
    clar = {"market": "United States", "focus": ["cost"], "_research_context": {
        "purpose": "choose a platform for a software team",
        "focus": ["cost", "reliability", "integrations", "support", "privacy"],
        "constraints": ["A condition that remains in model context"],
    }}
    text = pipeline._intake_summary(["AWS", "Azure"], clar, "Deep")
    assert text == ("Preparing Deep research on AWS and Azure. "
                    "Goal: choose a platform for a software team. "
                    "Priorities: cost, reliability, integrations (+2 more); market: United States.")
    assert "constraints" not in text
    assert "support" not in text and "privacy" not in text


@pytest.mark.parametrize("market, expected", [
    (None, "United States"), ("", "United States"), ("  No preference  ", "United States"),
    ("Global", "Global"), ("EMEA", "EMEA"),
    ("English-speaking North American teams", "English-speaking North American teams"),
])
def test_summary_defaults_only_unspecified_markets(market, expected):
    text = pipeline._intake_summary(["Notion"], {"market": market}, "Expert")
    assert text == f"Preparing Expert research on Notion. Market: {expected}."
    assert "Goal:" not in text and "Priorities:" not in text


async def test_first_planning_message_is_clean_while_model_keeps_all_context(offline):
    task = pipeline.create_task("Compare Notion and Obsidian", "quick")
    task = pipeline.submit_scope(task["taskId"], "roughly", task["scopeRevision"],
                                 "Research only Obsidian, for a small software team")
    assert task["ok"]
    task = pipeline.submit_scope(task["taskId"], "yes", task["scopeRevision"])
    task = pipeline.submit_clarify(task["taskId"], {"products": ["Obsidian"]},
                                   revision=task["clarificationRevision"])
    task = pipeline.submit_clarify(task["taskId"], {"market": "EMEA"},
                                   revision=task["clarificationRevision"])
    task = pipeline.submit_clarify(task["taskId"], {}, action="start",
                                   revision=task["clarificationRevision"])
    assert task["ok"]
    stored = db.get_task(task["taskId"])
    clar = stored["clarifications"]
    clar["_research_context"] = {"purpose": "choose a tool for a small software team",
                                  "focus": ["cost", "reliability", "integrations", "support"],
                                  "constraints": ["Retain this detailed constraint for the model"]}
    assert db.update_task_clarify(task["taskId"], clar)
    before = json.dumps(clar, sort_keys=True)
    events = [event async for event in pipeline.run_pipeline(task["taskId"])]
    first = next(event["data"] for event in events if event["type"] == "thought")
    assert first["kind"] == "plan" and first["expert"] == pipeline.DIRECTOR
    assert first["text"] == ("Preparing Quick research on Obsidian. "
                             "Goal: choose a tool for a small software team. "
                             "Priorities: cost, reliability, integrations (+1 more); market: EMEA.")
    assert "Notion" not in first["text"]
    assert not any(token in first["text"] for token in ("{", "}", "Confirmed research context", "_scope", "User corrections"))
    plan_prompts = [messages for kind, messages in offline.prompts if kind == "plan"]
    assert len(plan_prompts) == 1
    model_input = "\n".join(message["content"] for message in plan_prompts[0])
    assert "Confirmed research context" in model_input
    assert "Retain this detailed constraint for the model" in model_input
    assert "Research only Obsidian, for a small software team" in model_input
    assert '"products": ["Obsidian"]' in model_input
    assert '"market": "EMEA"' in model_input
    assert sum(kind == "dispatch" for kind, _ in offline.operations) == 1
    assert json.dumps(db.get_task(task["taskId"])["clarifications"], sort_keys=True) == before
    assert any(event["type"] == "done" for event in events)
