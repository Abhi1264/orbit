from __future__ import annotations

import json
import random
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from probelens.seed.catalog import apply_stockout_risk, generate_products
from probelens.seed.load_clickhouse import ClickHouseSink
from probelens.seed.population import generate_users
from probelens.seed.scenarios import Scenarios
from probelens.seed.simulate import EVENT_COLUMNS, Simulator
from probelens.tracking import taxonomy as t
from probelens.tracking.amplitude import AmplitudeSink
from probelens.tracking.mapping import AmplitudeMapper, UserTraits, epoch_ms
from probelens.tracking.pipeline import EventPipeline, SinkReport

T0 = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
PRICES = {11: 1299.0, 12: 1199.0}
TRAITS = {42: UserTraits("organic", date(2026, 8, 1), "card")}
API_KEY = "0123456789abcdef0123456789abcdef"

_BASE: dict[str, Any] = {
    "user_id": 42,
    "session_id": 7,
    "platform": "android",
    "device_type": "mobile",
    "app_version": "5.2.0",
    "country": "IN",
    "city": "Pune",
    "city_tier": "tier2",
    "traffic_source": "organic",
    "user_type": "returning",
    "experiments": {},
    "product_id": 0,
    "category": "",
    "subcategory": "",
    "order_id": 0,
    "order_value": 0.0,
    "payment_method": "",
    "payment_gateway": "",
    "failure_reason": "",
    "return_reason": "",
    "search_query": "",
    "delivery_days": 0,
    "properties": "",
}
SHIRT = {"product_id": 11, "category": "men", "subcategory": "shirts"}
JEANS = {"product_id": 12, "category": "men", "subcategory": "jeans"}
CARD = {"payment_method": "card", "payment_gateway": "razorpay"}


def row(name: str, seconds: int, start: datetime = T0, **fields: Any) -> tuple:
    values = {
        **_BASE,
        "event_id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{name}:{seconds}:{sorted(fields.items())}")),
        "event_name": name,
        "timestamp": start + timedelta(seconds=seconds),
        **fields,
    }
    return tuple(values[c] for c in EVENT_COLUMNS)


def purchase_session(start: datetime = T0) -> list[tuple]:
    day = 86400
    line_1 = {"order_id": 501, "order_value": 1200.0, "payment_method": "card", "delivery_days": 3}
    line_2 = {**line_1, "order_value": 1150.5}
    return [
        row("home_view", 0, start),
        row("search", 10, start, search_query="linen shirt", category="men"),
        row("search_result_view", 20, start, search_query="linen shirt", category="men"),
        row(
            "product_view",
            30,
            start,
            properties=json.dumps({"source": "search", "search_query": "linen shirt"}),
            **SHIRT,
        ),
        row("product_view", 40, start, **JEANS),
        row("add_to_cart", 50, start, **SHIRT),
        row("add_to_cart", 60, start, experiments={"checkout_v2": "treatment"}, **JEANS),
        row("checkout_started", 70, start, order_value=2498.0),
        row("payment_started", 80, start, order_value=2498.0, **CARD),
        row("payment_failed", 90, start, failure_reason="otp_failed", **CARD),
        row("payment_started", 100, start, order_value=2498.0, **CARD),
        row("payment_success", 110, start, order_id=501, order_value=2400.0, **CARD),
        row("order_completed", 120, start, **line_1, **SHIRT),
        row("order_completed", 125, start, **line_2, **JEANS),
        row("delivery_completed", 3 * day, start, **line_1, **SHIRT),
        row("delivery_completed", 3 * day + 3600, start, **line_2, **JEANS),
        row("return_initiated", 5 * day, start, return_reason="size_fit", **line_2, **JEANS),
    ]


def mapper() -> AmplitudeMapper:
    return AmplitudeMapper(PRICES, TRAITS)


def test_purchase_session_maps_to_tracking_plan_names() -> None:
    events = mapper().map(purchase_session())
    assert [e.event_type for e in events] == [
        t.HOME_PAGE_VIEWED,
        t.PRODUCT_SEARCHED,
        t.SEARCH_RESULTS_VIEWED,
        t.SEARCH_RESULT_CLICKED,
        t.PRODUCT_VIEWED,
        t.PRODUCT_VIEWED,
        t.PRODUCT_ADDED_TO_CART,
        t.PRODUCT_ADDED_TO_CART,
        t.CHECKOUT_STARTED,
        t.PAYMENT_STARTED,
        t.PAYMENT_FAILED,
        t.PAYMENT_STARTED,
        t.PAYMENT_COMPLETED,
        t.ORDER_PLACED,
        t.ORDER_DELIVERED,
        t.RETURN_INITIATED,
    ]
    for e in events:
        assert set(e.event_properties) <= set(t.PLAN_BY_NAME[e.event_type].properties), e.event_type


def test_event_properties_carry_real_values() -> None:
    by_type: dict[str, list] = {}
    for e in mapper().map(purchase_session()):
        by_type.setdefault(e.event_type, []).append(e)

    click = by_type[t.SEARCH_RESULT_CLICKED][0].event_properties
    assert click == {
        "query": "linen shirt",
        "product_id": "11",
        "category": "men",
        "subcategory": "shirts",
        "price": 1299.0,
        "traffic_source": "organic",
    }
    carts = [e.event_properties for e in by_type[t.PRODUCT_ADDED_TO_CART]]
    assert [(c["cart_value"], c["item_count"]) for c in carts] == [(1299.0, 1), (2498.0, 2)]
    attempts = [
        e.event_properties["attempt_number"]
        for name in (t.PAYMENT_STARTED, t.PAYMENT_FAILED, t.PAYMENT_COMPLETED)
        for e in by_type[name]
    ]
    assert sorted(attempts) == [1, 1, 2, 2]
    assert by_type[t.PAYMENT_FAILED][0].event_properties["failure_reason"] == "otp_failed"


def test_order_lines_fold_into_one_order_with_orbit_revenue() -> None:
    events = mapper().map(purchase_session())
    [order] = [e for e in events if e.event_type == t.ORDER_PLACED]
    assert order.revenue == 2350.5  # sum of order_completed lines: Orbit's revenue definition
    assert order.currency == "INR" and order.revenue_type == "purchase"
    assert order.event_properties["order_value"] == 2350.5
    assert order.event_properties["item_count"] == 2
    assert order.event_properties["product_ids"] == ["11", "12"]
    assert order.event_properties["order_id"] == "501"
    [delivered] = [e for e in events if e.event_type == t.ORDER_DELIVERED]
    assert delivered.event_properties["delivery_days"] == 3
    assert delivered.time == epoch_ms(T0 + timedelta(days=3, hours=1))


def test_sessions_identity_and_attribution() -> None:
    events = mapper().map(purchase_session())
    in_session = [e for e in events if e.event_type not in (t.ORDER_DELIVERED, t.RETURN_INITIATED)]
    after = [e for e in events if e.event_type in (t.ORDER_DELIVERED, t.RETURN_INITIATED)]
    assert {e.session_id for e in in_session} == {epoch_ms(T0)}
    assert {e.session_id for e in after} == {-1}
    assert all(e.event_properties.get("traffic_source") == "organic" for e in in_session)
    assert all("traffic_source" not in e.event_properties for e in after)
    assert {e.user_id for e in events} == {"42"}
    assert events[0].platform == "Android" and events[0].app_version == "5.2.0"


def test_user_properties_are_sent_once_then_only_changes() -> None:
    events = mapper().map(purchase_session())
    assert events[0].user_properties == {
        "$set": {
            "city_tier": "tier2",
            "customer_type": "returning",
            "device_type": "mobile",
            "acquisition_channel": "organic",
            "preferred_payment_method": "card",
            "signup_date": "2026-08-01",
        }
    }
    changes = [e.user_properties for e in events[1:] if e.user_properties]
    assert changes == [{"$set": {"experiment_checkout_v2": "treatment"}}]


def test_insert_ids_are_stable_and_unique() -> None:
    first = [e.insert_id for e in mapper().map(purchase_session())]
    again = [e.insert_id for e in mapper().map(purchase_session())]
    shuffled_rows = purchase_session()
    random.Random(3).shuffle(shuffled_rows)
    shuffled = [e.insert_id for e in mapper().map(shuffled_rows)]
    assert first == again == shuffled
    assert len(set(first)) == len(first)
    # A reseed with another end date replays the same event_ids on other days: not duplicates.
    shifted = [e.insert_id for e in mapper().map(purchase_session(T0 + timedelta(days=1)))]
    assert not set(first) & set(shifted)


SIM_END = date(2026, 9, 27)
SIM_START = SIM_END - timedelta(days=20)


def simulate() -> tuple[list[list[tuple]], AmplitudeMapper]:
    sc = Scenarios(start=SIM_START, end=SIM_END)
    rng = random.Random(11)
    products = apply_stockout_risk(rng, generate_products(rng, 200))
    users = generate_users(
        rng, 500, SIM_START, SIM_END, campaign_start=sc.day(sc.paid_social_campaign_start_days_before_end)
    )
    batches = list(Simulator(rng, users, products, SIM_START, SIM_END, sc).run())
    traits = {u.id: UserTraits(u.acquisition_source, u.signup_date, u.payment_method) for u in users}
    return batches, AmplitudeMapper({p.id: p.price for p in products}, traits)


@pytest.fixture(scope="module")
def sim() -> tuple[list[list[tuple]], AmplitudeMapper]:
    return simulate()


def test_simulator_is_deterministic_and_marks_search_clicks(sim) -> None:
    batches, _ = sim
    again, _ = simulate()
    assert batches == again
    cols = {c: i for i, c in enumerate(EVENT_COLUMNS)}
    sessions: dict[int, list[tuple]] = {}
    for r in (r for b in batches for r in b):
        sessions.setdefault(r[cols["session_id"]], []).append(r)
    clicks = 0
    for rows in sessions.values():
        for r in rows:
            if not r[cols["properties"]]:
                continue
            assert r[cols["event_name"]] == "product_view"
            clicks += 1
            query = json.loads(r[cols["properties"]])["search_query"]
            [results] = [x for x in rows if x[cols["event_name"]] == "search_result_view"]
            assert results[cols["search_query"]] == query
            assert results[cols["category"]] == r[cols["category"]]
            assert next(x for x in rows if x[cols["event_name"]] == "product_view") is r
    assert clicks > 0


def test_simulated_events_conform_to_the_plan(sim) -> None:
    batches, mapper_ = sim
    orbit_names = {r[1] for b in batches for r in b}
    sources = {spec.source for spec in t.TRACKING_PLAN if spec.source}
    assert sources == orbit_names

    revenue = 0.0
    seen: set[str] = set()
    keys: set[str] = set()
    for batch in batches:
        for e in mapper_.map(batch):
            spec = t.PLAN_BY_NAME[e.event_type]
            assert spec.source, e.event_type
            assert set(e.event_properties) <= set(spec.properties), e.event_type
            assert e.insert_id not in seen
            seen.add(e.insert_id)
            keys |= set(e.event_properties) | set((e.user_properties or {}).get("$set", {}))
            revenue += e.revenue or 0.0
    orbit_revenue = sum(
        r[EVENT_COLUMNS.index("order_value")] for b in batches for r in b if r[1] == "order_completed"
    )
    assert revenue == pytest.approx(orbit_revenue, abs=0.05)
    sensitive = {"email", "name", "phone", "password", "token", "address", "ip", "cvv", "pan"}
    assert not {k for k in keys if sensitive & set(k.split("_"))}


class _StubHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(body)  # type: ignore[attr-defined]
        status, payload = self.server.respond(body)  # type: ignore[attr-defined]
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


@contextmanager
def stub_amplitude(respond: Callable[[dict], tuple[int, dict]]) -> Iterator[tuple[Any, str]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.requests = []  # type: ignore[attr-defined]
    server.respond = respond  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}/batch"
    finally:
        server.shutdown()
        server.server_close()


def accepts(body: dict) -> tuple[int, dict]:
    if not body["events"]:
        return 400, {"code": 400, "error": "Request missing required field", "missing_field": "events"}
    return 200, {"code": 200, "events_ingested": len(body["events"])}


def rejects_key(body: dict) -> tuple[int, dict]:
    return 400, {"code": 400, "error": f"Invalid API key: {body['api_key']}"}


def probe_ok_then(respond: Callable[[dict], tuple[int, dict]]) -> Callable[[dict], tuple[int, dict]]:
    return lambda body: accepts(body) if not body["events"] else respond(body)


class FakeClickHouse:
    def __init__(self, fail: bool = False) -> None:
        self.inserted: list[tuple] = []
        self.fail = fail

    def insert(self, table: str, rows: list[tuple], column_names: list[str]) -> None:
        if self.fail:
            raise ConnectionError("ClickHouse unavailable")
        assert table == "events" and column_names == EVENT_COLUMNS
        self.inserted.extend(rows)


def test_amplitude_sink_delivers_through_the_sdk(sim) -> None:
    batches, mapper_ = sim
    days = batches[:3]
    expected = [e for b in days for e in AmplitudeMapper({}, {}).map(b)]
    with stub_amplitude(accepts) as (server, url):
        sink = AmplitudeSink(API_KEY, mapper_, server_url=url, flush_size=200)
        ch = FakeClickHouse()
        store, amp = EventPipeline([sink], store=ClickHouseSink(ch, batch_rows=1)).run(days)
        recent = sink.recent()

    assert store.ok and store.rows == sum(len(b) for b in days) == len(ch.inserted)
    assert amp.ok, amp.detail
    assert amp.sent == amp.delivered == len(expected) and amp.failed == amp.unconfirmed == 0
    uploads = [r for r in server.requests if r["events"]]
    sent = [e for r in uploads for e in r["events"]]
    assert len(sent) == amp.sent
    assert len({e["insert_id"] for e in sent}) == len(sent)
    assert all(r["api_key"] == API_KEY and r["options"] == {"min_id_length": 1} for r in uploads)
    first = sent[0]
    assert {"event_type", "user_id", "time", "insert_id", "session_id", "event_properties"} <= set(first)
    orders = [e for e in sent if e["event_type"] == t.ORDER_PLACED]
    assert orders and all(o["revenue"] > 0 and o["currency"] == "INR" for o in orders)
    assert recent and {e["amplitude"] for e in recent} == {"delivered"}


def test_rejected_key_sends_nothing_and_does_not_leak_it() -> None:
    with stub_amplitude(rejects_key) as (server, url):
        sink = AmplitudeSink(API_KEY, mapper(), server_url=url)
        ch = FakeClickHouse()
        store, amp = EventPipeline([sink], store=ClickHouseSink(ch, batch_rows=1)).run([purchase_session()])

    assert len(server.requests) == 1  # the key check only
    assert store.ok and len(ch.inserted) == len(purchase_session())
    assert not amp.ok and amp.sent == 0 and amp.skipped == len(purchase_session())
    assert "rejected the API key" in amp.detail and API_KEY not in amp.detail


def test_amplitude_outage_never_blocks_clickhouse() -> None:
    def outage(body: dict) -> tuple[int, dict]:
        return 503, {"code": 503, "error": "Service unavailable"}

    sessions = [purchase_session(T0 + timedelta(days=d)) for d in range(4)]
    with stub_amplitude(probe_ok_then(outage)) as (_, url):
        sink = AmplitudeSink(API_KEY, mapper(), server_url=url)
        ch = FakeClickHouse()
        store, amp = EventPipeline([sink], store=ClickHouseSink(ch, batch_rows=1)).run(sessions)

    assert store.ok and len(ch.inserted) == sum(len(s) for s in sessions)
    assert not amp.ok
    assert amp.delivered == 0 and amp.failed == amp.sent > 0
    assert amp.skipped == 2 * len(purchase_session())  # stopped after two batches with nothing delivered
    assert amp.detail.startswith("Stopped sending")


def test_silent_drops_are_bounded_by_the_stall_timeout() -> None:
    # The SDK drops events without a callback when the key is rejected mid-run.
    with stub_amplitude(probe_ok_then(rejects_key)) as (_, url):
        sink = AmplitudeSink(API_KEY, mapper(), server_url=url, stall_seconds=0.3)
        sessions = [purchase_session(T0 + timedelta(days=d)) for d in range(3)]
        [amp] = EventPipeline([sink]).run(sessions)

    assert not amp.ok and amp.delivered == 0
    assert amp.unconfirmed == amp.sent > 0
    assert "no response" in amp.detail


def test_events_stamped_in_the_future_are_deferred() -> None:
    now = T0 + timedelta(days=4)
    with stub_amplitude(accepts) as (server, url):
        sink = AmplitudeSink(API_KEY, mapper(), server_url=url, clock=now.timestamp)
        [amp] = EventPipeline([sink]).run([purchase_session()])

    sent = {e["event_type"] for r in server.requests for e in r["events"]}
    assert t.ORDER_DELIVERED in sent and t.RETURN_INITIATED not in sent
    assert amp.ok and amp.deferred == 1 and amp.delivered == amp.sent


class RecordingSink:
    def __init__(self, name: str = "recording", fail_on: int | None = None) -> None:
        self.name = name
        self.batches: list[list[tuple]] = []
        self.fail_on = fail_on
        self.closed = False

    def write(self, rows: list[tuple]) -> None:
        if self.fail_on is not None and len(self.batches) + 1 == self.fail_on:
            raise RuntimeError("destination exploded")
        self.batches.append(rows)

    def close(self) -> SinkReport:
        self.closed = True
        return SinkReport(self.name, ok=True, rows=sum(len(b) for b in self.batches))


def test_failing_sink_is_detached_and_reported() -> None:
    flaky, healthy = RecordingSink("flaky", fail_on=2), RecordingSink("healthy")
    ch = FakeClickHouse()
    batches = [[row("home_view", i)] for i in range(4)]
    store, flaky_report, healthy_report = EventPipeline(
        [flaky, healthy], store=ClickHouseSink(ch, batch_rows=1)
    ).run(batches)

    assert len(ch.inserted) == 4 and store.ok
    assert len(flaky.batches) == 1 and not flaky_report.ok
    assert "destination exploded" in flaky_report.detail
    assert len(healthy.batches) == 4 and healthy_report.ok


def test_store_failure_stops_the_run_and_closes_sinks() -> None:
    sink = RecordingSink()
    pipeline = EventPipeline([sink], store=ClickHouseSink(FakeClickHouse(fail=True), batch_rows=1))
    with pytest.raises(ConnectionError):
        pipeline.run([[row("home_view", 0)]])
    assert sink.closed and sink.batches == []


def test_sinks_only_receive_committed_batches() -> None:
    sink = RecordingSink()
    ch = FakeClickHouse()
    pipeline = EventPipeline([sink], store=ClickHouseSink(ch, batch_rows=3))
    pipeline.write([row("home_view", 0), row("home_view", 1)])
    assert sink.batches == [] and ch.inserted == []
    pipeline.write([row("home_view", 2)])
    assert len(sink.batches) == 2 and len(ch.inserted) == 3  # forwarded per day batch, after the insert
    pipeline.write([row("home_view", 3)])
    pipeline.close()
    assert len(sink.batches) == 3 and len(ch.inserted) == 4
