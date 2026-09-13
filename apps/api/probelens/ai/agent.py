"""Analyst orchestration: pick a mode, run it, audit it.

LLM mode is a bounded tool-calling loop. The model never sees raw data; it sees
one-line tool summaries and must return a structured answer whose facts cite
tool call ids. Demo mode runs the fixed playbooks. Both are persisted to
`ai_runs` so every answer can be replayed with its evidence.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime

import structlog
from pydantic import ValidationError
from sqlalchemy.orm import Session

from probelens.ai import demo
from probelens.ai.provider import ChatProvider, get_provider
from probelens.ai.schemas import AnalystAnswer, AskContext, AskResponse, Mode, ToolCallRecord
from probelens.ai.tools import TOOLS, ToolContext, run_tool
from probelens.analytics.dimensions import DIMENSIONS
from probelens.analytics.meta import _dimension_values, get_meta
from probelens.analytics.metrics import METRICS
from probelens.config import get_settings
from probelens.models import AiRun, User

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are the product analyst for Threadline, an Indian fashion e-commerce store. You answer
questions from product managers using ONLY the tools provided. You never state a number you did not get
from a tool in this conversation.

Working method:
1. For "why did X change" questions: call get_metric_summary, then root_cause over the period that looks
   wrong (baseline = 28 days before), then breakdown_metric on the top candidate's dimension. Call
   list_anomalies first when the question is vague about dates; the monitor knows when a move started, and
   you should anchor the period to it.
2. For "what is / how is X" questions: get_metric_summary, and breakdown_metric if a dimension is named or
   the move is large.
3. For funnel questions: run_funnel. For experiment questions: list_experiments then experiment_results. For
   "what needs attention": list_anomalies, list_investigations, list_releases.
4. Use plan_query if you are unsure how the user's words map to metric or dimension keys.
5. Stop calling tools once you can answer. Do not repeat a call with the same arguments.

Answer rules:
- Distinguish FACTS (numbers from tools, each citing the tool call id), INFERENCES (your interpretation,
with a confidence and the tool calls it rests on) and RECOMMENDATIONS (actions with a priority).
- A release or experiment that coincides with a change is timing evidence, not proof. Say so.
- Prefer relative changes and percentage points for rates; give the scope and date range with every number.
- Be concrete and short. No preamble, no restating the question.

When you are done, reply with ONLY a JSON object matching this schema (no markdown):
{
  "summary": "2-3 sentence answer",
  "facts": [{"text": "...", "source": "<tool call id>"}],
  "inferences": [{"text": "...", "confidence": "low|medium|high", "basis": ["<tool call id>", ...]}],
  "candidates": [{"title": "...", "confidence": "low|medium|high", "evidence": "...",
                  "kind": "segment|release|experiment|mix_shift", "href": null}],
  "recommendations": [{"text": "...", "priority": "now|next|later"}],
  "follow_ups": ["question the user could ask next", ...],
  "links": [{"label": "...", "href": "/analytics?metric=..."}],
  "caveats": ["..."]
}
Links: /analytics?metric=<key>&from=YYYY-MM-DD&to=YYYY-MM-DD[&breakdown=<dim>] ; /experiments/<id> ;
/investigations/<id> ; /funnels.
"""


def _vocabulary(tctx: ToolContext) -> str:
    metrics = "; ".join(f"{k}: {m.label} ({m.format.value})" for k, m in METRICS.items())
    dims = "; ".join(
        f"{k} [{', '.join(vals[:8])}{'…' if len(vals) > 8 else ''}]" if vals else k
        for k in DIMENSIONS
        for vals in [tctx.dimension_values.get(k, [])]
    )
    return (
        f"Latest day with data: {tctx.today.isoformat()}. Treat it as today.\n"
        f"Metric keys: {metrics}\n"
        f"Dimension keys and example values: {dims}"
    )


def _context_note(ctx: AskContext) -> str:
    parts = []
    if ctx.metric:
        parts.append(f"metric={ctx.metric}")
    if ctx.date_from and ctx.date_to:
        parts.append(f"date range {ctx.date_from}..{ctx.date_to}")
    if ctx.filters:
        parts.append("filters " + ", ".join(f.describe() for f in ctx.filters))
    if ctx.investigation_id:
        parts.append(f"investigation #{ctx.investigation_id}")
    if ctx.experiment_id:
        parts.append(f"experiment id {ctx.experiment_id}")
    return (
        ("The user is looking at: " + "; ".join(parts) + ". Default to it when the question is implicit.")
        if parts
        else ""
    )


def build_tool_context(db: Session) -> ToolContext:
    meta = get_meta()
    return ToolContext(db=db, today=meta.data_end or date.today(), dimension_values=_dimension_values())


def _parse_answer(text: str) -> AnalystAnswer:
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body[body.find("{") :]
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in reply")
    return AnalystAnswer.model_validate_json(body[start : end + 1])


def run_llm(
    provider: ChatProvider, question: str, ctx: AskContext, tctx: ToolContext
) -> tuple[AnalystAnswer, list[ToolCallRecord], dict[str, int | None]]:
    tools_schema = [t.openai_schema() for t in TOOLS.values()]
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _vocabulary(tctx)},
    ]
    note = _context_note(ctx)
    messages.append({"role": "user", "content": (note + "\n\n" if note else "") + question})
    calls: list[ToolCallRecord] = []
    usage: dict[str, int | None] = {"prompt_tokens": 0, "completion_tokens": 0}
    seen: set[str] = set()

    max_steps = get_settings().llm_max_tool_steps
    for step in range(max_steps):
        turn = provider.chat(messages, tools_schema)
        usage["prompt_tokens"] = (usage["prompt_tokens"] or 0) + (turn.prompt_tokens or 0)
        usage["completion_tokens"] = (usage["completion_tokens"] or 0) + (turn.completion_tokens or 0)
        if not turn.tool_calls:
            try:
                return _parse_answer(turn.content or ""), calls, usage
            except (ValueError, ValidationError) as exc:
                messages.append(turn.raw_message)
                messages.append(
                    {
                        "role": "user",
                        "content": f"Your reply was not valid JSON for the schema ({exc}). "
                        "Reply with only the JSON object.",
                    }
                )
                continue
        messages.append(turn.raw_message)
        for tc in turn.tool_calls:
            sig = tc.name + json.dumps(tc.arguments, sort_keys=True)
            call_id = f"c{len(calls) + 1}"
            if sig in seen:
                rec = ToolCallRecord(
                    id=call_id,
                    name=tc.name,
                    args=tc.arguments,
                    summary="",
                    ms=0,
                    error="Duplicate call skipped",
                )
            else:
                seen.add(sig)
                rec = run_tool(tc.name, tc.arguments, tctx, call_id)
            calls.append(rec)
            content = f"[{rec.id}] " + (f"ERROR: {rec.error}" if rec.error else rec.summary)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
        if step == max_steps - 2:
            messages.append(
                {"role": "user", "content": "Tool budget nearly exhausted; answer now with the JSON object."}
            )

    # Budget exhausted: force a final answer without tools.
    messages.append(
        {"role": "user", "content": "Answer now with only the JSON object using the evidence you have."}
    )
    turn = provider.chat(messages, None, json_response=True)
    return _parse_answer(turn.content or ""), calls, usage


def _answer_summary_for_audit(answer: AnalystAnswer) -> dict:
    return answer.model_dump(mode="json")


def ask(db: Session, user: User, question: str, ctx: AskContext, mode: Mode | None = None) -> AskResponse:
    t0 = time.perf_counter()
    provider = get_provider() if mode != "demo" else None
    effective: Mode = "llm" if provider else "demo"
    model = provider.model if provider else "playbook"
    calls: list[ToolCallRecord] = []
    usage: dict[str, int | None] = {"prompt_tokens": None, "completion_tokens": None}
    error = ""
    try:
        tctx = build_tool_context(db)
        if provider:
            try:
                answer, calls, usage = run_llm(provider, question, ctx, tctx)
            except Exception as exc:  # provider outage or malformed output: degrade, don't fail
                log.warning("ai_llm_failed_falling_back", error=str(exc)[:300])
                error = f"LLM failed ({type(exc).__name__}); answered with the deterministic analyst."
                effective, model = "demo", "playbook"
                answer, calls = demo.run_demo(question, ctx, tctx)
                answer.caveats.insert(0, error)
        else:
            answer, calls = demo.run_demo(question, ctx, tctx)
    except Exception as exc:
        # Even a broken playbook must leave an audit row.
        error = f"{type(exc).__name__}: {exc}"[:500]
        log.exception("ai_ask_failed")
        answer = AnalystAnswer(
            summary="The analyst could not complete this question.",
            caveats=[error],
            follow_ups=["What needs attention right now?", "Why did conversion fall last week?"],
        )
    latency = int((time.perf_counter() - t0) * 1000)
    # Persist without the bulky tool payloads; the response carries them.
    run = AiRun(
        user_id=user.id,
        question=question,
        mode=effective,
        model=model,
        tool_calls=[c.model_dump(mode="json", exclude={"data"}) for c in calls],
        response=_answer_summary_for_audit(answer),
        latency_ms=latency,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        error=error,
        created_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    log.info(
        "ai_ask",
        run_id=run.id,
        mode=effective,
        model=model,
        tools=[c.name for c in calls],
        latency_ms=latency,
        error=error or None,
    )
    return AskResponse(
        run_id=run.id,
        mode=effective,
        model=model,
        question=question,
        answer=answer,
        tool_calls=calls,
        latency_ms=latency,
        created_at=run.created_at,
    )
