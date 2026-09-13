"""Decision memo: a Markdown document a PM could paste into a doc as-is.

Generated from the readout with no LLM involved, so it is reproducible and
every number in it can be traced to a query. The AI analyst can later draft
narrative around it, but the facts come from here.
"""

from __future__ import annotations

from probelens.analytics.metrics import format_value, get_metric
from probelens.experiments.analysis import ExperimentResults, MetricReadout


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def _metric_table(m: MetricReadout, control: str) -> list[str]:
    fmt = get_metric(m.metric_key).format
    lines = [
        f"**{m.label}** ({'primary' if m.role == 'primary' else 'guardrail'}; "
        f"{'higher' if m.higher_is_better else 'lower'} is better)",
        "",
        "| Variant | Users | Value | 95% CI | vs control | p |",
        "|---|---:|---:|---|---|---:|",
    ]
    for v in m.variants:
        c = next((x for x in m.comparisons if x.variant == v.key), None)
        ci = (
            f"{format_value(fmt, v.ci_low)} – {format_value(fmt, v.ci_high)}" if v.ci_low is not None else "–"
        )
        if v.key == control:
            lines.append(f"| {v.key} (control) | {v.users:,} | {format_value(fmt, v.value)} | {ci} | – | – |")
        elif c:
            flag = " ✱" if c.significant else ""
            lines.append(
                f"| {v.key} | {v.users:,} | {format_value(fmt, v.value)} | {ci} | "
                f"{_pct(c.rel_diff)} ({_pct(c.rel_ci_low)} to "
                f"{_pct(c.rel_ci_high)}){flag} | {c.p_value:.3g} |"
            )
        else:
            lines.append(f"| {v.key} | {v.users:,} | {format_value(fmt, v.value)} | {ci} | – | – |")
    lines.append("")
    return lines


def build_memo(
    *,
    name: str,
    hypothesis: str,
    owner: str,
    status: str,
    results: ExperimentResults,
    recorded_decision: str | None = None,
    recorded_reason: str = "",
) -> str:
    r = results
    rec = r.recommendation
    ex = r.exposure
    primary = r.metrics[0]
    lines: list[str] = []
    lines += [f"# Decision memo: {name}", ""]
    lines += [
        f"**Owner:** {owner}  ",
        f"**Status:** {status}  ",
        f"**Window:** {r.window_start:%d %b %Y} – {r.window_end:%d %b %Y} ({ex.days_running} days), "
        f"outcomes through {r.as_of:%d %b %Y}  ",
        f"**Exposed users:** {ex.total_users:,} ("
        + ", ".join(f"{k} {v:,}" for k, v in sorted(ex.by_variant.items()))
        + ")",
        "",
    ]
    lines += ["## Hypothesis", "", hypothesis.strip(), ""]

    lines += ["## Recommendation", ""]
    decision_word = (recorded_decision or rec.decision).upper()
    lines.append(f"**{decision_word}** — {rec.headline}.")
    if recorded_decision and recorded_decision != rec.decision:
        lines.append("")
        lines.append(
            f"_The recorded decision ({recorded_decision}) differs from the rule-based recommendation "
            f"({rec.decision}); the rationale below explains why._"
        )
    lines.append("")
    if recorded_reason:
        lines += ["### Rationale", "", recorded_reason.strip(), ""]
    lines += ["### Why", ""]
    lines += [f"- {x}" for x in rec.reasons]
    if rec.risks:
        lines += ["", "### Risks and caveats", ""]
        lines += [f"- {x}" for x in rec.risks]
    lines.append("")

    lines += ["## Results", ""]
    for m in r.metrics:
        lines += _metric_table(m, r.control)
    lines.append(
        "✱ significant at the 5% level (two-sided). "
        "Intervals are 95% and account for users having many sessions."
    )
    lines.append("")

    if r.segments:
        lines += ["## Segments (primary metric)", ""]
        for s in r.segments:
            lines += [
                f"**By {s.label.lower()}**",
                "",
                "| Segment | Users | Control | Treatment | Lift | Significant |",
                "|---|---:|---:|---:|---:|---|",
            ]
            fmt = get_metric(primary.metric_key).format
            for row in s.rows:
                lines.append(
                    f"| {row.segment} | {row.users:,} | {format_value(fmt, row.control)} | "
                    f"{format_value(fmt, row.treatment)} | "
                    f"{_pct(row.rel_diff)} | {'yes' if row.significant else 'no'} |"
                )
            lines.append("")
        lines.append(
            "_Segment results are exploratory: with several segments, some will look significant by chance. "
            "Treat them as hypotheses for a follow-up test, not as ship criteria._"
        )
        lines.append("")

    lines += ["## Validity checks", ""]
    for c in rec.checks:
        lines.append(f"- {'✅' if c.passed else '⚠️'} **{c.name}** — {c.detail}")
    lines.append("")

    if r.notes:
        lines += ["## Notes", ""] + [f"- {n}" for n in r.notes] + [""]

    lines += [
        "## Method",
        "",
        "Users are analysed under the variant of their first exposure. Metrics are ratios of per-user sums, "
        "with variance from the delta method, so session-level rates are not over-confident when users have "
        "several sessions. Differences use a two-sided z-test at α = 0.05; the sample-ratio check is a "
        "chi-square goodness of fit against the configured split. The ship/iterate/stop recommendation is "
        "rule-based and fully listed under validity checks.",
        "",
    ]
    return "\n".join(lines)
