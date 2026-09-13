"""The LLM loop with a scripted provider: tool calls are executed and recorded, duplicates are
skipped, malformed final answers are retried, and the budget is enforced. No network, no DB."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from probelens.ai import agent
from probelens.ai.provider import ChatTurn, ToolCall
from probelens.ai.schemas import AskContext, ToolCallRecord
from probelens.ai.tools import ToolContext


class ScriptedProvider:
    model = "scripted"

    def __init__(self, turns: list[ChatTurn]) -> None:
        self.turns = list(turns)
        self.seen_messages: list[list[dict[str, Any]]] = []

    def chat(self, messages, tools=None, *, json_response=False, temperature=0.1) -> ChatTurn:
        self.seen_messages.append([dict(m) for m in messages])
        if not self.turns:
            raise AssertionError("provider called more times than scripted")
        return self.turns.pop(0)


GOOD_ANSWER = {
    "summary": "Conversion fell 10%.",
    "facts": [{"text": "Conversion 4.4% -> 4.0%", "source": "c1"}],
    "inferences": [{"text": "Paid social drove it", "confidence": "medium", "basis": ["c1"]}],
    "candidates": [],
    "recommendations": [{"text": "Review campaign", "priority": "now"}],
    "follow_ups": ["What needs attention?"],
    "links": [],
    "caveats": [],
}


@pytest.fixture
def tctx() -> ToolContext:
    return ToolContext(db=None, today=date(2026, 9, 13), dimension_values={"platform": ["android"]})  # type: ignore[arg-type]


@pytest.fixture
def stub_tools(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    executed: list[tuple[str, dict]] = []

    def fake_run_tool(name: str, raw_args: dict, ctx: ToolContext, call_id: str) -> ToolCallRecord:
        executed.append((name, raw_args))
        return ToolCallRecord(id=call_id, name=name, args=raw_args, summary=f"{name} ok", ms=1, data={"x": 1})

    monkeypatch.setattr(agent, "run_tool", fake_run_tool)
    return executed


def test_tool_calls_are_executed_then_answer_parsed(tctx: ToolContext, stub_tools) -> None:
    provider = ScriptedProvider(
        [
            ChatTurn(
                content=None,
                tool_calls=[ToolCall("x1", "get_metric_summary", {"metric": "conversion"})],
                raw_message={"role": "assistant", "tool_calls": []},
            ),
            ChatTurn(content=json.dumps(GOOD_ANSWER), prompt_tokens=10, completion_tokens=5),
        ]
    )
    answer, calls, usage = agent.run_llm(provider, "why did conversion fall?", AskContext(), tctx)
    assert [c.name for c in calls] == ["get_metric_summary"]
    assert calls[0].id == "c1"
    assert answer.summary == "Conversion fell 10%."
    assert answer.facts[0].source == "c1"
    assert usage["prompt_tokens"] == 10
    # The tool result went back to the model tagged with the call id it should cite.
    tool_msgs = [m for m in provider.seen_messages[-1] if m.get("role") == "tool"]
    assert tool_msgs and tool_msgs[0]["content"].startswith("[c1] get_metric_summary ok")


def test_duplicate_calls_are_skipped(tctx: ToolContext, stub_tools) -> None:
    same = ToolCall("x", "list_anomalies", {"status": "open"})
    provider = ScriptedProvider(
        [
            ChatTurn(content=None, tool_calls=[same, ToolCall("y", "list_anomalies", {"status": "open"})]),
            ChatTurn(content=json.dumps(GOOD_ANSWER)),
        ]
    )
    _, calls, _ = agent.run_llm(provider, "q", AskContext(), tctx)
    assert len(calls) == 2
    assert calls[1].error == "Duplicate call skipped"
    assert len(stub_tools) == 1


def test_malformed_final_answer_is_retried(tctx: ToolContext, stub_tools) -> None:
    provider = ScriptedProvider(
        [
            ChatTurn(content="Sure! Here is my analysis in prose."),
            ChatTurn(content="```json\n" + json.dumps(GOOD_ANSWER) + "\n```"),
        ]
    )
    answer, _, _ = agent.run_llm(provider, "q", AskContext(), tctx)
    assert answer.summary == "Conversion fell 10%."
    # The retry told the model what was wrong.
    assert any("not valid JSON" in m.get("content", "") for m in provider.seen_messages[-1])


def test_budget_forces_a_final_answer(tctx: ToolContext, stub_tools, monkeypatch: pytest.MonkeyPatch) -> None:
    from probelens.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_max_tool_steps", 3)
    endless = [
        ChatTurn(content=None, tool_calls=[ToolCall(f"x{i}", "list_releases", {"platform": p})])
        for i, p in enumerate(["android", "ios", "web"])
    ]
    provider = ScriptedProvider([*endless, ChatTurn(content=json.dumps(GOOD_ANSWER))])
    answer, calls, _ = agent.run_llm(provider, "q", AskContext(), tctx)
    assert len(calls) == 3
    assert answer.summary
    assert provider.turns == []  # the forced final call consumed the last scripted turn


def test_context_note_is_prepended(tctx: ToolContext, stub_tools) -> None:
    provider = ScriptedProvider([ChatTurn(content=json.dumps(GOOD_ANSWER))])
    ctx = AskContext(metric="payment_success_rate", date_from=date(2026, 9, 1), date_to=date(2026, 9, 7))
    agent.run_llm(provider, "why?", ctx, tctx)
    user_msg = next(m for m in provider.seen_messages[0] if m["role"] == "user")
    assert "metric=payment_success_rate" in user_msg["content"]
    assert user_msg["content"].endswith("why?")
