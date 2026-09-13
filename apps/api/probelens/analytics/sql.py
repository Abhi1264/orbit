"""SQL fragments shared by the metric, funnel and anomaly engines."""

from typing import Any

from probelens.analytics.dimensions import Filter, compile_filters, split_by_scope

DATE_WINDOW = "event_date BETWEEN {d_from:Date} AND {d_to:Date}"

# Emitted days after the session that produced the order; excluded from
# session-scoped queries so a session is attributed to a single day.
POST_PURCHASE_EVENTS = ("delivery_completed", "return_initiated", "return_completed")

NOT_POST_PURCHASE = f"event_name NOT IN {POST_PURCHASE_EVENTS}"


def session_where(filters: list[Filter], params: dict[str, Any]) -> str:
    """WHERE clause for a per-session rollup. Session-scoped filters apply to
    every row; event-scoped filters select whole sessions that contain a
    matching event, so a filter like payment_method = upi keeps the full
    session rather than only its payment events."""
    session_filters, event_filters = split_by_scope(filters)
    ws = compile_filters(session_filters, prefix="s")
    params.update(ws.params)
    where = f"{DATE_WINDOW} AND {NOT_POST_PURCHASE} AND {ws.sql}"
    if event_filters:
        we = compile_filters(event_filters, prefix="e")
        params.update(we.params)
        where += f" AND session_id IN (SELECT session_id FROM events WHERE {DATE_WINDOW} AND {we.sql})"
    return where
