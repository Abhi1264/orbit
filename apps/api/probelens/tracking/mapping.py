from __future__ import annotations

import json
import uuid
from collections import namedtuple
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

from probelens.analytics.sql import POST_PURCHASE_EVENTS
from probelens.seed.simulate import EVENT_COLUMNS
from probelens.tracking import taxonomy as t

Row = namedtuple("Row", EVENT_COLUMNS)

# Never change: insert_ids derived from it are what lets Amplitude drop re-sent events.
_INSERT_ID_NAMESPACE = uuid.UUID("3b8f0a52-6c1e-4f7d-9a24-5e0c7b1d9f63")

_NO_SESSION = -1


@dataclass(frozen=True)
class UserTraits:
    acquisition_channel: str
    signup_date: date | None
    preferred_payment_method: str


@dataclass
class AmplitudeEvent:
    event_type: str
    user_id: str
    time: int
    insert_id: str
    session_id: int
    event_properties: dict[str, Any]
    user_properties: dict[str, Any] | None = None
    platform: str | None = None
    app_version: str | None = None
    country: str | None = None
    city: str | None = None
    revenue: float | None = None
    revenue_type: str | None = None
    currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def insert_id(event_type: str, user_id: int, time_ms: int, source_event_ids: Sequence[str]) -> str:
    # Time is part of the key: reseeding with another end date replays the same event_ids on shifted days.
    key = "|".join([event_type, str(user_id), str(time_ms), *source_event_ids])
    return str(uuid.uuid5(_INSERT_ID_NAMESPACE, key))


def epoch_ms(ts: datetime) -> int:
    if ts.tzinfo is None:  # ClickHouse returns naive UTC
        ts = ts.replace(tzinfo=UTC)
    return int(ts.timestamp() * 1000)


def search_click_query(properties: str) -> str | None:
    if not properties.startswith("{"):
        return None
    try:
        data = json.loads(properties)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("source") != "search":
        return None
    return data.get("search_query") or None


def _money(value: float) -> float:
    return round(value, 2)


def _payment(r: Row) -> dict[str, Any]:
    return {"payment_method": r.payment_method, "payment_gateway": r.payment_gateway}


class AmplitudeMapper:
    def __init__(self, prices: Mapping[int, float], traits: Mapping[int, UserTraits]) -> None:
        self._prices = prices
        self._traits = traits
        self._sent: dict[int, dict[str, Any]] = {}

    def map(self, rows: Iterable[Sequence[Any]]) -> list[AmplitudeEvent]:
        sessions: dict[int, list[Row]] = {}
        for raw in rows:
            row = Row._make(raw)
            sessions.setdefault(row.session_id, []).append(row)
        for session in sessions.values():
            session.sort(key=lambda r: epoch_ms(r.timestamp))
        events: list[AmplitudeEvent] = []
        for session in sorted(sessions.values(), key=lambda s: epoch_ms(s[0].timestamp)):
            events.extend(self._map_session(session))
        return events

    def _map_session(self, rows: list[Row]) -> list[AmplitudeEvent]:
        live = [r for r in rows if r.event_name not in POST_PURCHASE_EVENTS]
        session_id = epoch_ms(live[0].timestamp) if live else _NO_SESSION
        lines: dict[tuple[str, int], list[Row]] = {}
        for r in rows:
            if r.event_name in ("order_completed", "delivery_completed"):
                lines.setdefault((r.event_name, r.order_id), []).append(r)

        cart: list[float | None] = []
        attempt = 0
        out: list[AmplitudeEvent] = []
        for r in rows:
            name = r.event_name
            if name == "home_view":
                out.append(self._event(r, t.HOME_PAGE_VIEWED, {}, session_id))
            elif name in ("search", "search_result_view"):
                event_type = t.PRODUCT_SEARCHED if name == "search" else t.SEARCH_RESULTS_VIEWED
                props = {"query": r.search_query, "category": r.category}
                out.append(self._event(r, event_type, props, session_id))
            elif name == "product_view":
                product = self._product(r)
                query = search_click_query(r.properties)
                if query:
                    click = {"query": query, **product}
                    out.append(self._event(r, t.SEARCH_RESULT_CLICKED, click, session_id))
                out.append(self._event(r, t.PRODUCT_VIEWED, product, session_id))
            elif name == "add_to_wishlist":
                out.append(self._event(r, t.PRODUCT_ADDED_TO_WISHLIST, self._product(r), session_id))
            elif name == "add_to_cart":
                product = self._product(r)
                cart.append(product["price"])
                known = None not in cart
                props = {
                    **product,
                    "cart_value": _money(sum(cart)) if known else None,
                    "item_count": len(cart),
                }
                out.append(self._event(r, t.PRODUCT_ADDED_TO_CART, props, session_id))
            elif name == "checkout_started":
                props = {"cart_value": _money(r.order_value), "item_count": len(cart) or None}
                out.append(self._event(r, t.CHECKOUT_STARTED, props, session_id))
            elif name == "payment_started":
                attempt += 1
                props = {**_payment(r), "cart_value": _money(r.order_value), "attempt_number": attempt}
                out.append(self._event(r, t.PAYMENT_STARTED, props, session_id))
            elif name == "payment_failed":
                props = {**_payment(r), "failure_reason": r.failure_reason, "attempt_number": attempt or None}
                out.append(self._event(r, t.PAYMENT_FAILED, props, session_id))
            elif name == "payment_success":
                props = {
                    **_payment(r),
                    "order_id": str(r.order_id),
                    "payment_amount": _money(r.order_value),
                    "attempt_number": attempt or None,
                }
                out.append(self._event(r, t.PAYMENT_COMPLETED, props, session_id))
            elif name == "order_completed":
                group = lines[(name, r.order_id)]
                if r is group[0]:
                    out.append(self._order_placed(group, session_id))
            elif name == "delivery_completed":
                group = lines[(name, r.order_id)]
                if r is group[-1]:
                    out.append(self._order_delivered(group))
            elif name in ("return_initiated", "return_completed"):
                event_type = t.RETURN_INITIATED if name == "return_initiated" else t.RETURN_COMPLETED
                props = {
                    "order_id": str(r.order_id),
                    "product_id": str(r.product_id),
                    "category": r.category,
                    "subcategory": r.subcategory,
                    "item_value": _money(r.order_value),
                    "return_reason": r.return_reason,
                    "payment_method": r.payment_method,
                }
                out.append(self._event(r, event_type, props, _NO_SESSION))
        return out

    def _product(self, r: Row) -> dict[str, Any]:
        return {
            "product_id": str(r.product_id),
            "category": r.category,
            "subcategory": r.subcategory,
            "price": self._prices.get(r.product_id),
        }

    def _order_placed(self, lines: list[Row], session_id: int) -> AmplitudeEvent:
        first = lines[0]
        value = _money(sum(line.order_value for line in lines))
        props = {
            "order_id": str(first.order_id),
            "order_value": value,
            "item_count": len(lines),
            "payment_method": first.payment_method,
            "product_ids": [str(line.product_id) for line in lines],
            "categories": sorted({line.category for line in lines if line.category}),
        }
        return self._event(
            first,
            t.ORDER_PLACED,
            props,
            session_id,
            sources=lines,
            revenue=value,
            revenue_type="purchase",
            currency=t.CURRENCY,
        )

    def _order_delivered(self, lines: list[Row]) -> AmplitudeEvent:
        last = lines[-1]
        props = {
            "order_id": str(last.order_id),
            "order_value": _money(sum(line.order_value for line in lines)),
            "item_count": len(lines),
            "delivery_days": last.delivery_days,
            "payment_method": last.payment_method,
        }
        return self._event(last, t.ORDER_DELIVERED, props, _NO_SESSION, sources=lines)

    def _event(
        self,
        r: Row,
        event_type: str,
        props: dict[str, Any],
        session_id: int,
        *,
        sources: Sequence[Row] = (),
        **fields: Any,
    ) -> AmplitudeEvent:
        time_ms = epoch_ms(r.timestamp)
        if session_id != _NO_SESSION and r.traffic_source:
            props["traffic_source"] = r.traffic_source
        source_ids = sorted(str(s.event_id) for s in sources) if sources else [str(r.event_id)]
        return AmplitudeEvent(
            event_type=event_type,
            user_id=str(r.user_id),
            time=time_ms,
            insert_id=insert_id(event_type, r.user_id, time_ms, source_ids),
            session_id=session_id,
            event_properties={k: v for k, v in props.items() if v not in (None, "", [])},
            user_properties=self._user_property_changes(r),
            platform=t.PLATFORM_LABELS.get(r.platform, r.platform) or None,
            app_version=r.app_version or None,
            country=r.country or None,
            city=r.city or None,
            **fields,
        )

    def _user_property_changes(self, r: Row) -> dict[str, Any] | None:
        props: dict[str, Any] = {
            "city_tier": r.city_tier,
            "customer_type": r.user_type,
            "device_type": r.device_type,
        }
        traits = self._traits.get(r.user_id)
        if traits:
            props["acquisition_channel"] = traits.acquisition_channel
            props["preferred_payment_method"] = traits.preferred_payment_method
            if traits.signup_date:
                props["signup_date"] = traits.signup_date.isoformat()
        for key, variant in (r.experiments or {}).items():
            props[f"{t.EXPERIMENT_USER_PROPERTY_PREFIX}{key}"] = variant
        sent = self._sent.setdefault(r.user_id, {})
        changed = {k: v for k, v in props.items() if v and sent.get(k) != v}
        if not changed:
            return None
        sent.update(changed)
        return {"$set": changed}
