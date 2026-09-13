"""Deterministic analyst: fixed playbooks over the same tools the LLM uses.

This is what runs when no LLM key is configured (and what the acceptance test
pins). Each playbook decides which tools to call from the parsed question,
then composes an `AnalystAnswer` whose every fact cites the tool call that
produced it. No prose is generated from anything the tools did not return.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from probelens.ai import planner
from probelens.ai.schemas import (
    AnalystAnswer,
    AskContext,
    CandidateOut,
    Fact,
    Inference,
    LinkOut,
    RecommendationItem,
    ToolCallRecord,
)
from probelens.ai.tools import ToolContext, run_tool
from probelens.analytics.dimensions import DIMENSIONS, Filter
from probelens.analytics.metrics import format_value, get_metric
from probelens.analytics.rootcause import _areas_touch_metric

Conf = str  # "low" | "medium" | "high"


@dataclass
class Trace:
    ctx: ToolContext
    calls: list[ToolCallRecord] = field(default_factory=list)

    def call(self, name: str, **args: Any) -> ToolCallRecord:
        rec = run_tool(name, _jsonable(args), self.ctx, f"c{len(self.calls) + 1}")
        self.calls.append(rec)
        return rec


def _jsonable(args: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(args, default=_default))


def _default(o: Any) -> Any:
    if isinstance(o, date):
        return o.isoformat()
    if hasattr(o, "model_dump"):
        return o.model_dump(exclude_none=True)
    raise TypeError(type(o).__name__)


def _pct(v: float | None, signed: bool = True) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def _d(s: str) -> str:
    return date.fromisoformat(s).strftime("%-d %b")


def _scope(filters: list[Filter]) -> str:
    return ", ".join(f.describe() for f in filters) or "store-wide"


def explore_href(
    metric: str,
    filters: list[Filter] | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    breakdown: str | None = None,
) -> str:
    sp: dict[str, str] = {"metric": metric}
    if filters:
        sp["f"] = json.dumps([f.model_dump(exclude_none=True) for f in filters], separators=(",", ":"))
    if date_from:
        sp["from"] = str(date_from)
    if date_to:
        sp["to"] = str(date_to)
    if breakdown:
        sp["breakdown"] = breakdown
    return "/analytics?" + urlencode(sp)


def funnel_href(filters: list[Filter], date_from: date, date_to: date, breakdown: str | None) -> str:
    sp: dict[str, str] = {"from": str(date_from), "to": str(date_to)}
    if filters:
        sp["segments"] = json.dumps(
            [{"label": _scope(filters), "filters": [f.model_dump(exclude_none=True) for f in filters]}],
            separators=(",", ":"),
        )
    if breakdown:
        sp["breakdown"] = breakdown
    return "/funnels?" + urlencode(sp)


def _ok(rec: ToolCallRecord) -> bool:
    return rec.error is None and rec.data is not None


def _dominant_dimension(question: str, metric: str) -> str:
    """Dimension to show when the user didn't name one: what typically explains this metric."""
    m = get_metric(metric)
    if "payment" in m.key:
        return "payment_method"
    if "search" in m.key:
        return "category"
    if "return" in m.key or "delivery" in m.key:
        return "category"
    return "platform"


def _empty(question: str, why: str) -> AnalystAnswer:
    return AnalystAnswer(
        summary=why,
        caveats=[
            "The analyst only reports numbers returned by its tools; nothing was fabricated to fill the gap."
        ],
        follow_ups=[
            "Why did conversion fall last week?",
            "Payment success rate on Android over the last 30 days",
            "What needs attention right now?",
        ],
    )


def run_demo(
    question: str, ask_ctx: AskContext, tctx: ToolContext
) -> tuple[AnalystAnswer, list[ToolCallRecord]]:
    plan = planner.parse(question, tctx.today, tctx.dimension_values)
    trace = Trace(tctx)

    # Page context fills in what the question left implicit.
    metric = plan.metric or ask_ctx.metric
    filters = plan.filters or list(ask_ctx.filters)
    if not plan.dates.explicit and ask_ctx.date_from and ask_ctx.date_to:
        plan.dates.date_from, plan.dates.date_to = ask_ctx.date_from, ask_ctx.date_to
    if ask_ctx.experiment_id and plan.intent in ("what", "experiment") and plan.metric is None:
        plan.intent = "experiment"

    if plan.intent == "attention":
        answer = _attention(trace, plan)
    elif plan.intent == "experiment":
        answer = _experiment(trace, plan, ask_ctx)
    elif plan.intent == "funnel":
        answer = _funnel(trace, plan, filters)
    elif plan.intent == "why":
        answer = _why(trace, plan, metric or "conversion", filters, ask_ctx)
    elif plan.intent == "compare":
        answer = _what(trace, plan, metric or "conversion", filters, compare=True)
    else:
        answer = _what(trace, plan, metric or "conversion", filters)

    if (
        plan.unresolved
        and len(plan.unresolved) <= 4
        and plan.intent not in ("experiment", "attention", "funnel")
    ):
        answer.caveats.append(
            "Words not mapped to a metric, dimension or date and ignored: " + ", ".join(plan.unresolved) + "."
        )
    return answer, trace.calls


def _what(
    trace: Trace, plan: planner.Plan, metric: str, filters: list[Filter], compare: bool = False
) -> AnalystAnswer:
    m = get_metric(metric)
    d0, d1 = plan.dates.date_from, plan.dates.date_to
    c_sum = trace.call("get_metric_summary", metric=metric, date_from=d0, date_to=d1, filters=filters)
    if not _ok(c_sum):
        return _empty("", f"Could not compute {m.label}: {c_sum.error}")
    s = c_sum.data or {}
    facts = [Fact(text=c_sum.summary, source=c_sum.id)]
    if s.get("min_day") and s.get("max_day") and s["min_day"]["bucket"] != s["max_day"]["bucket"]:
        facts.append(
            Fact(
                text=f"Daily range: low {format_value(m.format, s['min_day']['value'])} on "
                f"{_d(s['min_day']['bucket'][:10])}, "
                f"high {format_value(m.format, s['max_day']['value'])} on {_d(s['max_day']['bucket'][:10])}.",
                source=c_sum.id,
            )
        )

    inferences: list[Inference] = []
    recs: list[RecommendationItem] = []
    links = [
        LinkOut(
            label=f"Open {m.label} in Analytics", href=explore_href(metric, filters, d0, d1, plan.breakdown)
        )
    ]
    breakdown = plan.breakdown or (_dominant_dimension("", metric) if compare else None)

    rel = s.get("rel_change")
    if rel is not None:
        good = (rel > 0) == m.higher_is_better
        size = abs(rel)
        if size >= 0.05:
            inferences.append(
                Inference(
                    text=f"A {_pct(rel)} move over {(d1 - d0).days + 1} days is larger than normal "
                    "week-to-week drift for "
                    f"{m.label.lower()}; treat it as a real change rather than noise.",
                    confidence="medium" if size < 0.15 else "high",
                    basis=[c_sum.id],
                )
            )
            if not good:
                recs.append(
                    RecommendationItem(
                        text=f"Ask “why did {m.label.lower()} change” to decompose the move by segment and "
                        "correlate it with releases.",
                        priority="now",
                    )
                )
                if breakdown is None:
                    breakdown = _dominant_dimension("", metric)
        elif size < 0.02:
            inferences.append(
                Inference(
                    text=f"{m.label} is flat versus the previous window; no action indicated from this view.",
                    confidence="medium",
                    basis=[c_sum.id],
                )
            )

    if breakdown:
        c_bd = trace.call(
            "breakdown_metric", metric=metric, dimension=breakdown, date_from=d0, date_to=d1, filters=filters
        )
        if _ok(c_bd):
            rows = (c_bd.data or {}).get("rows", [])
            facts.append(Fact(text=c_bd.summary, source=c_bd.id))
            valued = [r for r in rows if r["value"] is not None and r["share"] >= 0.05]
            if len(valued) >= 2:
                hi = max(valued, key=lambda r: r["value"])
                lo = min(valued, key=lambda r: r["value"])
                if hi is not lo and lo["value"]:
                    gap = (hi["value"] - lo["value"]) / lo["value"]
                    inferences.append(
                        Inference(
                            text=f"{hi['segment']} outperforms {lo['segment']} on {m.label.lower()} by "
                            f"{_pct(gap, signed=False)} relative "
                            f"({format_value(m.format, hi['value'])} vs "
                            f"{format_value(m.format, lo['value'])}).",
                            confidence="high" if gap > 0.1 else "medium",
                            basis=[c_bd.id],
                        )
                    )
                moved = [r for r in valued if r["rel_change"] is not None]
                if moved:
                    worst = min(
                        moved, key=lambda r: r["rel_change"] if m.higher_is_better else -r["rel_change"]
                    )
                    if abs(worst["rel_change"]) >= 0.05:
                        inferences.append(
                            Inference(
                                text=f"The largest deterioration is in {worst['segment']} "
                                f"({_pct(worst['rel_change'])} versus the previous window, "
                                f"{worst['share'] * 100:.0f}% of volume).",
                                confidence="medium",
                                basis=[c_bd.id],
                            )
                        )
            links.append(
                LinkOut(
                    label=f"{m.label} by {DIMENSIONS[breakdown].label.lower()}",
                    href=explore_href(metric, filters, d0, d1, breakdown),
                )
            )

    follow_ups = [
        f"Why did {m.label.lower()} change {plan.dates.phrase or 'in this period'}?",
        f"{m.label} by traffic source {plan.dates.phrase or 'last 14 days'}",
        f"Show the funnel for {_scope(filters)}" if filters else "Show the checkout funnel by platform",
    ]
    summary = c_sum.summary + "." if not c_sum.summary.endswith(".") else c_sum.summary
    return AnalystAnswer(
        summary=summary,
        facts=facts,
        inferences=inferences,
        recommendations=recs,
        follow_ups=follow_ups,
        links=links,
        caveats=[]
        if plan.dates.explicit
        else [
            f"No date range given; used {d0:%-d %b}–{d1:%-d %b} (the latest {(d1 - d0).days + 1} days of "
            "data)."
        ],
    )


def _dedupe(filters: list[Filter]) -> list[Filter]:
    seen: set[str] = set()
    out: list[Filter] = []
    for f in filters:
        k = json.dumps(f.model_dump(exclude_none=True), sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def _anomaly_covers_scope(anomaly: dict[str, Any], filters: list[Filter]) -> bool:
    """True unless an eq filter on the anomaly contradicts the question (UPI store-wide
    still explains 'on android'; platform=ios does not)."""
    if anomaly.get("scope") in (_scope(filters), "store-wide"):
        return True
    asked = {f.dimension: str(f.value) for f in filters if f.operator == "eq" and f.value is not None}
    have = {
        str(f.get("dimension")): str(f.get("value"))
        for f in (anomaly.get("filters") or [])
        if f.get("operator", "eq") == "eq" and f.get("value") is not None
    }
    return all(have[d] == asked[d] for d in have if d in asked)


def _as_date(v: date | str) -> date:
    return v if isinstance(v, date) else date.fromisoformat(v)


def _release_anchor(
    releases: list[dict[str, Any]], metric: str, filters: list[Filter], p0: date
) -> dict[str, Any] | None:
    """When the monitor only flags the last few days, the shipping date is the real start."""
    m = get_metric(metric)
    platforms = {str(f.value) for f in filters if f.dimension == "platform" and f.operator == "eq"}
    best: dict[str, Any] | None = None
    best_d: date | None = None
    for r in releases:
        rd = _as_date(r["release_date"])
        if r.get("status") == "planned" or rd >= p0 or (p0 - rd).days > 35:
            continue
        if platforms and r["platform"] not in platforms and r["platform"] != "all":
            continue
        if not _areas_touch_metric(m, list(r.get("affected_areas") or [])):
            continue
        if best_d is None or rd > best_d:
            best, best_d = r, rd
    return best


def _anchor_to_anomaly(
    anomalies: list[dict[str, Any]], filters: list[Filter], p0: date, p1: date
) -> dict | None:
    """The anomaly monitor knows when a move started; a 'why' about 'the last 7 days' should
    use that start, otherwise the baseline is polluted by the already-broken days."""
    best: dict[str, Any] | None = None
    for a in anomalies:
        a0, a1 = date.fromisoformat(a["period_start"]), date.fromisoformat(a["period_end"])
        if a1 < p0 or a0 > p1 or a0 >= p0 or (p0 - a0).days > 35:
            continue
        if not _anomaly_covers_scope(a, filters):
            continue
        if best is None or a0 < date.fromisoformat(best["period_start"]):
            best = a
    return best


def _why_candidates(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Top readout plus the lead release, which otherwise falls off once more slices rank higher."""
    shown = list(cands[:5])
    titles = {c["title"] for c in shown}
    lead = next(
        (c for c in cands if c.get("kind") == "release" and c.get("confidence") in ("high", "medium")),
        next((c for c in cands if c.get("kind") == "release"), None),
    )
    if lead and lead["title"] not in titles:
        shown.append(lead)
    return shown


def _merge_nearby_releases(
    cands: list[dict[str, Any]], releases: list[dict[str, Any]], metric: str, filters: list[Filter]
) -> list[dict[str, Any]]:
    """RCA only emits a release when a version slice ranks. A finished rollout still belongs here."""
    m = get_metric(metric)
    platforms = {str(f.value) for f in filters if f.dimension == "platform" and f.operator == "eq"}
    have = " ".join(c.get("title") or "" for c in cands)
    out = list(cands)
    for r in releases:
        if r.get("status") == "planned":
            continue
        if platforms and r["platform"] not in platforms and r["platform"] != "all":
            continue
        if not _areas_touch_metric(m, list(r.get("affected_areas") or [])):
            continue
        if r["version"] in have:
            continue
        title = f"Release {r['version']} ({r['platform']})"
        out.append(
            {
                "kind": "release",
                "title": title,
                "confidence": "medium",
                "summary": r.get("name") or title,
                "release_id": r["id"],
                "data": r,
            }
        )
        have += " " + r["version"]
    return out


def _drill_recommendation(m, top: dict[str, Any]) -> str:
    if "payment" in m.key:
        return (
            f"Drill into {top['title']}: break failures down by failure reason and gateway for that segment, "
            "and compare against the same days on the other platform."
        )
    if "search" in m.key:
        return f"Drill into {top['title']}: compare top search queries and zero-result rate for that segment."
    if "return" in m.key or "delivery" in m.key:
        return f"Drill into {top['title']}: break it down by return reason and category for that segment."
    return (
        f"Drill into {top['title']}: run the funnel for that segment to find which step is leaking, then "
        "check the releases and experiments touching it."
    )


def _why(
    trace: Trace, plan: planner.Plan, metric: str, filters: list[Filter], ask_ctx: AskContext
) -> AnalystAnswer:
    m = get_metric(metric)
    p0, p1 = plan.dates.date_from, plan.dates.date_to
    # A "why" over a long window would compare it against an even longer past; keep the period focused.
    if not plan.dates.explicit and (p1 - p0).days > 7:
        p0 = p1 - timedelta(days=6)

    facts: list[Fact] = []
    caveats: list[str] = []

    # Known anomalies first: they can re-anchor the period.
    c_an = trace.call("list_anomalies", status="all", metric=metric, limit=30)
    anomalies = (c_an.data or {}).get("anomalies", []) if _ok(c_an) else []
    anchor = (
        _anchor_to_anomaly(anomalies, filters, p0, p1)
        if not plan.dates.explicit or plan.dates.phrase in ("last 7 days", "this week", "last week")
        else None
    )
    if anchor:
        p0 = date.fromisoformat(anchor["period_start"])
        caveats.append(
            f"Period widened to {p0:%-d %b}–{p1:%-d %b}: the monitor flagged this move starting {p0:%-d %b}, "
            "so the baseline is taken from before it."
        )
    else:
        from sqlalchemy import select

        from probelens.models import Release

        rows = list(
            trace.ctx.db.scalars(
                select(Release).where(
                    Release.release_date < p0, Release.release_date >= p0 - timedelta(days=35)
                )
            )
        )
        hit = _release_anchor(
            [
                {
                    "version": r.version,
                    "release_date": r.release_date,
                    "platform": r.platform,
                    "status": getattr(r.status, "value", r.status),
                    "affected_areas": list(r.affected_areas or []),
                }
                for r in rows
            ],
            metric,
            filters,
            p0,
        )
        if hit:
            p0 = _as_date(hit["release_date"])
            caveats.append(
                f"Period widened to {p0:%-d %b}–{p1:%-d %b}: {hit['version']} shipped {p0:%-d %b}, "
                "so the baseline is taken from before it."
            )
    b1 = p0 - timedelta(days=1)
    b0 = b1 - timedelta(days=27)

    c_sum = trace.call("get_metric_summary", metric=metric, date_from=p0, date_to=p1, filters=filters)
    c_rc = trace.call(
        "root_cause",
        metric=metric,
        period_from=p0,
        period_to=p1,
        baseline_from=b0,
        baseline_to=b1,
        filters=filters,
    )
    if not _ok(c_rc):
        return _empty("", f"Root-cause decomposition failed: {c_rc.error}")
    rc = c_rc.data or {}
    overall = rc["overall"]
    cands = rc["candidates"]
    inferences: list[Inference] = []
    out_cands: list[CandidateOut] = []
    recs: list[RecommendationItem] = []
    caveats += list(rc.get("notes", []))
    links: list[LinkOut] = [
        LinkOut(label=f"{m.label} in Analytics", href=explore_href(metric, filters, b0, p1))
    ]

    rel = overall.get("rel_change")
    direction = "fell" if (rel or 0) < 0 else "rose"
    worse = rel is not None and ((rel < 0) == m.higher_is_better)
    facts.append(
        Fact(
            text=f"{m.label} ({_scope(filters)}) was {format_value(m.format, overall['period'])} over "
            f"{p0:%-d %b}–{p1:%-d %b} versus {format_value(m.format, overall['baseline'])} in the 28-day "
            f"baseline ({_pct(rel)}).",
            source=c_rc.id,
        )
    )
    if _ok(c_sum) and (c_sum.data or {}).get("previous") is not None:
        facts.append(
            Fact(text=c_sum.summary + " (versus the immediately preceding window).", source=c_sum.id)
        )

    if rel is None or abs(rel) < 0.02:
        return AnalystAnswer(
            summary=f"{m.label} did not move materially ({_pct(rel)}) in {p0:%-d %b}–{p1:%-d %b} against its "
            "28-day baseline; there is nothing to explain.",
            facts=facts,
            links=links,
            follow_ups=[f"{m.label} by platform last 14 days", "What needs attention right now?"],
            caveats=caveats,
        )

    # Segment / mix candidates: show the breakdown that backs the top one.
    seg = [c for c in cands if c["kind"] in ("segment", "mix_shift")]
    top = seg[0] if seg else None
    c_bd = None
    if top and top.get("dimension"):
        c_bd = trace.call(
            "breakdown_metric",
            metric=metric,
            dimension=top["dimension"],
            date_from=p0,
            date_to=p1,
            filters=filters,
        )
        if _ok(c_bd):
            facts.append(Fact(text=c_bd.summary, source=c_bd.id))

    c_rel = trace.call("list_releases", date_from=b0, date_to=p1)
    nearby = (c_rel.data or {}).get("releases", []) if _ok(c_rel) else []
    if nearby:
        facts.append(Fact(text=c_rel.summary, source=c_rel.id))
    cands = _merge_nearby_releases(cands, nearby, metric, filters)

    release_cands = [c for c in cands if c["kind"] == "release" and c["confidence"] in ("high", "medium")]
    lead_release = release_cands[0]["data"] if release_cands and release_cands[0].get("data") else None
    if lead_release is None and release_cands:
        lead_release = next(
            (r for r in rc.get("releases", []) if r["id"] == release_cands[0]["release_id"]), None
        )

    shown = _why_candidates(cands)
    for i, c in enumerate(shown):
        href = None
        if c["kind"] in ("segment", "mix_shift") and c.get("filters"):
            cf = _dedupe(filters + [Filter.model_validate(f) for f in c["filters"]])
            href = explore_href(metric, cf, b0, p1)
        elif c["kind"] == "release" and c.get("release_id"):
            href = explore_href(metric, filters, b0, p1, "app_version")
        elif c["kind"] == "mix_shift" and c.get("dimension"):
            href = explore_href(metric, filters, b0, p1, c["dimension"])
        elif c["kind"] == "experiment" and c.get("experiment_id"):
            href = f"/experiments/{c['experiment_id']}"
        out_cands.append(
            CandidateOut(
                title=c["title"], confidence=c["confidence"], evidence=c["summary"], kind=c["kind"], href=href
            )
        )
        if i >= 3 and c["kind"] != "release":
            continue
        basis = [c_rc.id] + (
            [c_bd.id] if c_bd and _ok(c_bd) and c["kind"] in ("segment", "mix_shift") else []
        )
        explained = c.get("explained")
        if c["kind"] == "segment" and explained is not None:
            text = (
                f"{c['title']} accounts for about {explained * 100:.0f}% of the overall change; the rate "
                "moved "
                "within that segment rather than its share of traffic."
            )
        elif c["kind"] == "mix_shift" and c.get("dimension") == "app_version":
            rel_match = [r for r in rc.get("releases", []) if r["version"] == c.get("key")]
            named = (
                " ("
                + ", ".join(f"{r['platform']} {r['version']} on {_d(r['release_date'])}" for r in rel_match)
                + ")"
                if rel_match
                else ""
            )
            text = (
                f"Version {c.get('key')}{named} rolled out across the scope during the period and runs below "
                "the baseline rate; read this as rollout evidence for that release, not a traffic-mix change."
            )
        elif c["kind"] == "mix_shift" and explained is not None:
            text = (
                f"{c['title']}: traffic mix shifted toward a lower-converting group, explaining about "
                f"{explained * 100:.0f}% of the change without any segment getting worse on its own."
            )
        elif c["kind"] == "release":
            text = f"Timing is consistent with {c['title']}: {c['summary']}"
        else:
            text = c["summary"]
        inferences.append(Inference(text=text, confidence=c["confidence"], basis=basis))

    # Only pull an experiment readout when the experiment actually measures this metric.
    exp_refs = [
        e
        for e in rc.get("experiments", [])
        if e["relevance"] in ("strong", "possible")
        and (e["primary_metric"] == metric or metric in (e.get("guardrail_metrics") or []))
    ]
    for e in exp_refs[:1]:
        c_exp = trace.call("experiment_results", experiment=e["key"])
        if _ok(c_exp):
            facts.append(Fact(text=c_exp.summary, source=c_exp.id))
            guard = [g for g in (c_exp.data or {}).get("metrics", []) if g["metric"] == metric]
            if guard and guard[0].get("direction") == "worse":
                inferences.append(
                    Inference(
                        text=f"Experiment {e['name']} shows {m.label.lower()} worse in treatment "
                        f"({_pct(guard[0]['rel_diff'])}); the experiment itself may be a contributor.",
                        confidence="medium",
                        basis=[c_exp.id],
                    )
                )
            elif guard:
                inferences.append(
                    Inference(
                        text=f"Experiment {e['name']} does not move {m.label.lower()} "
                        f"({_pct(guard[0]['rel_diff'])}, "
                        f"{guard[0]['direction']}), so it is unlikely to be the cause.",
                        confidence="medium",
                        basis=[c_exp.id],
                    )
                )

    overlapping = [
        a
        for a in anomalies
        if date.fromisoformat(a["period_end"]) >= p0 and date.fromisoformat(a["period_start"]) <= p1
    ]
    if overlapping:
        facts.append(
            Fact(
                text=f"The monitor already flagged {len(overlapping)} overlapping {m.label.lower()} "
                f"anomal{'y' if len(overlapping) == 1 else 'ies'}: "
                + "; ".join(f"{a['scope']} ({a['severity']}, {a['status']})" for a in overlapping[:3])
                + ".",
                source=c_an.id,
            )
        )
    c_inv = trace.call("list_investigations", status="active", metric=metric)
    open_inv = (c_inv.data or {}).get("investigations", []) if _ok(c_inv) else []
    for inv in open_inv[:2]:
        links.append(
            LinkOut(label=f"Investigation #{inv['id']}: {inv['title']}", href=f"/investigations/{inv['id']}")
        )
    if open_inv:
        facts.append(Fact(text=c_inv.summary, source=c_inv.id))

    # Recommendations follow from the candidate kinds, not from the metric name.
    if worse:
        if lead_release:
            r = lead_release
            areas = ", ".join(r.get("affected_areas") or []) or "the changed surface"
            if r["platform"] == "all":
                recs.append(
                    RecommendationItem(
                        text=f"Confirm the {r['version']} link: compare {m.label.lower()} on the days "
                        "before and "
                        f"after {_d(r['release_date'])} for sessions touching {areas}; a step change on the "
                        "release date points at the release, a gradual drift does not.",
                        priority="now",
                    )
                )
                recs.append(
                    RecommendationItem(
                        text=f"If the step change is there, roll {r['version']} back behind its feature "
                        "flag and "
                        "re-run the comparison; add the affected metric as a guardrail in its release "
                        "checklist.",
                        priority="now",
                    )
                )
            else:
                recs.append(
                    RecommendationItem(
                        text=f"Confirm the {r['platform']} {r['version']} link: break {m.label.lower()} "
                        "down by app "
                        f"version on {r['platform']} and compare users on {r['version']} against the prior "
                        "version over the same days.",
                        priority="now",
                    )
                )
                recs.append(
                    RecommendationItem(
                        text=f"If the version split confirms it, pause the {r['version']} rollout or ship a "
                        "hotfix, "
                        "and add a version guardrail to the release SOP.",
                        priority="now",
                    )
                )
                plat = [Filter(dimension="platform", operator="eq", value=r["platform"])]
                links.append(
                    LinkOut(
                        label=f"{m.label} by app version on {r['platform']}",
                        href=explore_href(metric, _dedupe(filters + plat), b0, p1, "app_version"),
                    )
                )
        mix = next(
            (c for c in cands[:3] if c["kind"] == "mix_shift" and c.get("dimension") != "app_version"), None
        )
        if mix:
            seg_label = mix["summary"].split(" moved from")[0]
            if mix.get("dimension") == "traffic_source":
                text = (
                    f"Treat the {seg_label} volume as a mix effect: report {m.label.lower()} excluding it "
                    "next to "
                    "the headline, and review the campaign's targeting and landing experience with growth."
                )
            else:
                text = (
                    f"Treat the shift toward {seg_label} as a mix effect: report {m.label.lower()} per "
                    "segment next "
                    "to the headline so the blended number is not read as a product regression."
                )
            recs.append(RecommendationItem(text=text, priority="now"))
        first_seg = next((c for c in cands[:4] if c["kind"] == "segment" and c["confidence"] != "low"), None)
        if first_seg:
            recs.append(
                RecommendationItem(
                    text=_drill_recommendation(m, first_seg), priority="next" if lead_release else "now"
                )
            )
        if not open_inv:
            recs.append(
                RecommendationItem(
                    text=f"Open an investigation scoped to {_scope(filters)} so the hypotheses and evidence "
                    "are "
                    "tracked in one place.",
                    priority="next",
                )
            )
        recs.append(
            RecommendationItem(
                text="Once fixed, keep the anomaly monitor on this scope for two weeks to confirm recovery.",
                priority="later",
            )
        )
    else:
        recs.append(
            RecommendationItem(
                text=f"Capture what drove the improvement ({top['title'] if top else 'see candidates'}) in "
                "the "
                "decision log so it can be repeated deliberately.",
                priority="next",
            )
        )

    if len([c for c in cands if c["kind"] == "segment"]) >= 2:
        caveats.append(
            "Segment contributions are computed one dimension at a time and overlap (the same users appear "
            "under platform, city tier and traffic source); they do not add up to 100%."
        )
    caveats.append(
        "Release and experiment correlations are timing evidence; confirm with a version or variant split "
        "before acting."
    )
    if (p1 - p0).days + 1 < 7:
        caveats.append(
            f"The period is only {(p1 - p0).days + 1} days; day-level rates are noisy at this volume."
        )

    lead = (
        f"{m.label} {direction} {_pct(abs(rel), signed=False)} "
        f"({format_value(m.format, overall['baseline'])} → {format_value(m.format, overall['period'])}) "
        f"in {p0:%-d %b}–{p1:%-d %b} versus its 28-day baseline."
    )
    if cands:
        heads = [f"{c['title']} ({c['confidence']} confidence)" for c in cands[:2]]
        lead += " Most likely drivers: " + " and ".join(heads) + "."
    if lead_release and not any(c["kind"] == "release" for c in cands[:2]):
        who = (
            lead_release["version"]
            if lead_release["platform"] == "all"
            else f"{lead_release['platform']} {lead_release['version']}"
        )
        lead += f" The {who} release lines up with the start of the move."

    follow_ups = []
    if top and top.get("filters") and top["kind"] == "segment":
        cf = _dedupe(filters + [Filter.model_validate(f) for f in top["filters"]])
        follow_ups.append(f"Show the funnel for {_scope(cf)} {plan.dates.phrase or 'last 7 days'}")
    if lead_release and lead_release["platform"] != "all":
        follow_ups.append(f"{m.label} by app version on {lead_release['platform']} last 14 days")
    follow_ups.append("What needs attention right now?")

    return AnalystAnswer(
        summary=lead,
        facts=facts,
        inferences=inferences,
        candidates=out_cands,
        recommendations=recs,
        follow_ups=follow_ups[:3],
        links=links,
        caveats=caveats,
    )


def _funnel(trace: Trace, plan: planner.Plan, filters: list[Filter]) -> AnalystAnswer:
    d0, d1 = plan.dates.date_from, plan.dates.date_to
    breakdown = plan.breakdown
    c_f = trace.call("run_funnel", date_from=d0, date_to=d1, filters=filters, breakdown=breakdown)
    if not _ok(c_f):
        return _empty("", f"Funnel query failed: {c_f.error}")
    series = (c_f.data or {}).get("series", [])
    facts = [Fact(text=c_f.summary, source=c_f.id)]
    inferences: list[Inference] = []
    recs: list[RecommendationItem] = []
    if series:
        base = series[0]
        for st in base["steps"][1:]:
            if st["step_conversion"] is not None:
                facts.append(
                    Fact(
                        text=f"{base['label']}: {st['sessions']:,} sessions reached {st['label']} "
                        f"({_pct(st['step_conversion'], signed=False)} of the previous step; "
                        f"{st['drop_off']:,} dropped).",
                        source=c_f.id,
                    )
                )
        if len(series) >= 2:
            # Which step differs most between the best and worst segment?
            best = max(series, key=lambda s: s["steps"][-1]["overall_conversion"] or 0)
            worst = min(series, key=lambda s: s["steps"][-1]["overall_conversion"] or 0)
            gaps = []
            for i in range(1, len(best["steps"])):
                a, b = best["steps"][i]["step_conversion"], worst["steps"][i]["step_conversion"]
                if a is not None and b is not None and b:
                    gaps.append((a / b - 1, best["steps"][i]["label"], a, b))
            if gaps:
                g = max(gaps, key=lambda x: abs(x[0]))
                inferences.append(
                    Inference(
                        text=f"The gap between {best['label']} and {worst['label']} concentrates at the "
                        f"step into {g[1]}: "
                        f"{_pct(g[2], signed=False)} vs {_pct(g[3], signed=False)} step conversion "
                        f"({_pct(g[0])} relative).",
                        confidence="high" if abs(g[0]) > 0.1 else "medium",
                        basis=[c_f.id],
                    )
                )
                recs.append(
                    RecommendationItem(
                        text=f"Investigate the {g[1].lower()} step for {worst['label']}: compare it against "
                        f"{best['label']} by app version and payment method.",
                        priority="now",
                    )
                )
        else:
            leak = base.get("biggest_leak")
            if leak:
                inferences.append(
                    Inference(
                        text=f"The largest loss is before {leak}; that transition sets the ceiling for "
                        "end-to-end conversion.",
                        confidence="medium",
                        basis=[c_f.id],
                    )
                )
                recs.append(
                    RecommendationItem(
                        text=f"Break the funnel down by platform and traffic source to see whether the leak "
                        f"before {leak.lower()} is uniform or concentrated.",
                        priority="next",
                    )
                )
    return AnalystAnswer(
        summary=c_f.summary.split(". ", 1)[0] + ". " + (inferences[0].text if inferences else ""),
        facts=facts,
        inferences=inferences,
        recommendations=recs,
        follow_ups=[
            "Why did checkout conversion change last week?",
            "Payment success rate by payment method last 14 days",
            "Funnel by traffic source last 30 days",
        ],
        links=[LinkOut(label="Open in Funnels", href=funnel_href(filters, d0, d1, breakdown))],
        caveats=[
            "Funnel steps are counted within a session and a 24-hour window; a user who returns the next "
            "day starts a new funnel."
        ],
    )


def _experiment(trace: Trace, plan: planner.Plan, ask_ctx: AskContext) -> AnalystAnswer:
    c_list = trace.call("list_experiments", status="all")
    exps = (c_list.data or {}).get("experiments", []) if _ok(c_list) else []
    chosen = None
    if ask_ctx.experiment_id:
        chosen = next((e for e in exps if e["id"] == ask_ctx.experiment_id), None)
    if chosen is None and exps:
        words = set(planner._norm(plan.experiment_hint or "").split()) | {w for w in plan.unresolved}
        words |= set(planner._norm(" ".join(plan.matched)).split())

        def score(e: dict[str, Any]) -> int:
            hay = planner._norm(e["name"] + " " + e["key"].replace("_", " "))
            return sum(1 for w in words if len(w) > 2 and w in hay)

        ranked = sorted(exps, key=score, reverse=True)
        chosen = ranked[0] if ranked and score(ranked[0]) > 0 else None
    if chosen is None:
        summary = "Which experiment? " + (
            "; ".join(f"{e['name']} ({e['status']})" for e in exps) if exps else "No experiments found."
        )
        return AnalystAnswer(
            summary=summary,
            facts=[Fact(text=c_list.summary, source=c_list.id)] if _ok(c_list) else [],
            follow_ups=[f"How is the {e['name']} experiment doing?" for e in exps[:3]],
            links=[LinkOut(label="Experiments", href="/experiments")],
        )
    c_res = trace.call("experiment_results", experiment=chosen["key"])
    if not _ok(c_res):
        return _empty("", f"Could not analyze {chosen['name']}: {c_res.error}")
    r = c_res.data or {}
    if r.get("status") == "draft":
        return AnalystAnswer(
            summary=c_res.summary,
            facts=[Fact(text=c_res.summary, source=c_res.id)],
            links=[LinkOut(label=chosen["name"], href=f"/experiments/{chosen['id']}")],
        )
    rec = r["recommendation"]
    exposure = r["exposure"]
    facts = [
        Fact(
            text=f"{chosen['name']}: {exposure['total_users']:,} users exposed over "
            f"{exposure['days_running']} days ({chosen['status']}).",
            source=c_res.id,
        )
    ]
    for mt in r["metrics"]:
        if mt["rel_diff"] is None:
            continue
        fmt = get_metric(mt["metric"]).format
        ci = mt["rel_ci"] or [None, None]
        facts.append(
            Fact(
                text=f"{mt['label']} ({mt['role']}): {format_value(fmt, mt['treatment'])} vs "
                f"{format_value(fmt, mt['control'])}, "
                f"{_pct(mt['rel_diff'])} (95% CI {_pct(ci[0])} to {_pct(ci[1])}, p={mt['p_value']:.3g}).",
                source=c_res.id,
            )
        )
    srm = next((c for c in rec["checks"] if c["name"] == "Sample ratio"), None)
    if srm:
        facts.append(Fact(text=f"Sample ratio check: {srm['detail']}", source=c_res.id))
    inferences = [Inference(text=rec["headline"], confidence=rec["confidence"], basis=[c_res.id])]
    inferences += [
        Inference(text=t, confidence=rec["confidence"], basis=[c_res.id]) for t in rec["reasons"][:3]
    ]
    recs = [
        RecommendationItem(
            text=f"Decision engine recommends: {rec['decision']}. "
            f"{rec['reasons'][0] if rec['reasons'] else ''}".strip(),
            priority="now",
        )
    ]
    recs += [RecommendationItem(text=risk, priority="next") for risk in rec.get("risks", [])[:2]]
    if r.get("recorded_decision"):
        facts.append(
            Fact(
                text=f"Recorded decision: {r['recorded_decision']}. {r.get('decision_reason', '')}".strip(),
                source=c_res.id,
            )
        )
    caveats = list(r.get("notes", []))
    caveats.append(
        "Lift is measured per user with delta-method intervals; the recommendation is rule-based and should "
        "be read with the guardrails, not instead of them."
    )
    return AnalystAnswer(
        summary=f"{chosen['name']}: {rec['headline']}",
        facts=facts,
        inferences=inferences,
        recommendations=recs,
        follow_ups=[
            f"Why did {get_metric(chosen['primary_metric']).label.lower()} change last week?",
            "Which experiments are running right now?",
            "What needs attention right now?",
        ],
        links=[LinkOut(label=f"Open {chosen['name']}", href=f"/experiments/{chosen['id']}")],
        caveats=caveats,
    )


def _days_after(a: date, b: date) -> str:
    n = (a - b).days
    return "the same day as" if n == 0 else f"{n} day{'s' if n != 1 else ''} after"


def _attention(trace: Trace, plan: planner.Plan) -> AnalystAnswer:
    c_an = trace.call("list_anomalies", status="all", limit=30)
    c_inv = trace.call("list_investigations", status="active")
    c_rel = trace.call(
        "list_releases", date_from=trace.ctx.today - timedelta(days=14), date_to=trace.ctx.today
    )
    anomalies = [
        a for a in ((c_an.data or {}).get("anomalies", []) if _ok(c_an) else []) if a["status"] != "resolved"
    ]
    invs = (c_inv.data or {}).get("investigations", []) if _ok(c_inv) else []
    releases = (c_rel.data or {}).get("releases", []) if _ok(c_rel) else []

    facts: list[Fact] = []
    inferences: list[Inference] = []
    recs: list[RecommendationItem] = []
    links: list[LinkOut] = [LinkOut(label="Anomaly inbox", href="/investigations")]

    high = [a for a in anomalies if a["severity"] == "high"]
    ongoing = [a for a in anomalies if a["ongoing"]]
    facts.append(
        Fact(
            text=f"{len(anomalies)} unresolved anomalies, {len(high)} high severity, "
            f"{len(ongoing)} still ongoing as of {trace.ctx.today:%-d %b}.",
            source=c_an.id,
        )
    )
    for a in anomalies[:5]:
        facts.append(Fact(text=a["text"] + ".", source=c_an.id))

    # Anomalies sharing a scope are usually one story.
    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in anomalies:
        by_scope[a["scope"]].append(a)
    clusters = sorted(
        ((k, v) for k, v in by_scope.items() if len(v) >= 2 and k != "store-wide"), key=lambda kv: -len(kv[1])
    )
    for scope, group in clusters[:2]:
        names = ", ".join(
            dict.fromkeys(f"{get_metric(a['metric']).label.lower()} {a['direction']}" for a in group)
        )
        inferences.append(
            Inference(
                text=f"{len(group)} anomalies share the scope {scope} ({names}); they most likely have one "
                "underlying cause rather than several.",
                confidence="medium",
                basis=[c_an.id],
            )
        )
    linked = {a["investigation_id"] for a in anomalies if a.get("investigation_id")}
    unlinked_high = [a for a in high if not a.get("investigation_id")]
    if invs:
        facts.append(Fact(text=c_inv.summary, source=c_inv.id))
        for inv in invs[:3]:
            links.append(LinkOut(label=f"#{inv['id']} {inv['title']}", href=f"/investigations/{inv['id']}"))
            scope = inv.get("scope") or "store-wide"
            matching = [a for a in anomalies if a["scope"] == scope]
            inferences.append(
                Inference(
                    text=(
                        f"Investigation #{inv['id']} ({inv['title']}) is already open on {scope}"
                        + (
                            f" and covers {len(matching)} unresolved "
                            f"anomal{'y' if len(matching) == 1 else 'ies'}"
                            if matching
                            else ""
                        )
                        + "; treat that thread as one story."
                    ),
                    confidence="medium",
                    basis=[c_inv.id] + ([c_an.id] if matching else []),
                )
            )
    if releases:
        facts.append(Fact(text=c_rel.summary, source=c_rel.id))
        # Any high anomaly on a platform that shipped a release just before it started?
        for a in high[:5]:
            for r in releases:
                start = date.fromisoformat(a["period_start"])
                rd = date.fromisoformat(r["release_date"])
                if 0 <= (start - rd).days <= 3 and (r["platform"] == "all" or r["platform"] in a["scope"]):
                    inferences.append(
                        Inference(
                            text=f"{get_metric(a['metric']).label} on {a['scope']} started moving "
                            f"{_days_after(start, rd)} {r['platform']} {r['version']} "
                            f"({', '.join(r['affected_areas'])}); check that release first.",
                            confidence="medium",
                            basis=[c_an.id, c_rel.id],
                        )
                    )
                    break

    for a in unlinked_high[:2]:
        recs.append(
            RecommendationItem(
                text=f"Open an investigation for {get_metric(a['metric']).label.lower()} on {a['scope']} (z "
                f"{a['zscore']:+.1f}, {a['severity']}); it has no owner yet.",
                priority="now",
            )
        )
    if linked:
        recs.append(
            RecommendationItem(
                text=f"{len(linked)} anomal{'y is' if len(linked) == 1 else 'ies are'} already under "
                "investigation; check those for updates before starting new work.",
                priority="next",
            )
        )
    if not anomalies:
        recs.append(
            RecommendationItem(
                text="No open anomalies; review running experiments and the funnel for slow drifts the "
                "monitor does not catch.",
                priority="later",
            )
        )

    if anomalies:
        a0 = anomalies[0]
        lead = (
            f"{len(anomalies)} open anomalies; the most severe is "
            f"{get_metric(a0['metric']).label.lower()} {a0['direction']} on {a0['scope']} "
            f"({format_value(get_metric(a0['metric']).format, a0['actual'])} vs expected "
            f"{format_value(get_metric(a0['metric']).format, a0['expected'])})."
        )
        if clusters:
            lead += f" {len(clusters[0][1])} of them share the scope {clusters[0][0]}."
    else:
        lead = "Nothing is flagged right now."
    return AnalystAnswer(
        summary=lead,
        facts=facts,
        inferences=inferences,
        recommendations=recs,
        follow_ups=[
            f"Why did {get_metric(a['metric']).label.lower()} change "
            f"{('on ' + a['scope']) if a['scope'] != 'store-wide' else ''} last week?".replace("  ", " ")
            for a in high[:2]
        ]
        + ["Which experiments are running right now?"],
        links=links,
        caveats=[
            "Severity reflects the size and persistence of the deviation, not business impact; weigh it "
            "against the segment's volume."
        ],
    )
