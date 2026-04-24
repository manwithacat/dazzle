"""Tests for GA4 sink + bridge (v0.61.0 Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from dazzle.compliance.analytics import (
    AnalyticsBridge,
    AnalyticsEvent,
    GA4MeasurementProtocolSink,
    SinkResult,
    TenantContext,
    build_bridge_from_spec,
    get_sink_factory,
    list_sink_names,
    match_topic_glob,
)
from dazzle.core.ir import (
    AnalyticsServerSideSpec,
    AnalyticsSpec,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeResponse:
    status_code: int
    text: str = ""


class _FakeAsyncClient:
    """Minimal async httpx stand-in — records calls, returns pre-seeded responses."""

    def __init__(self, responses: list[_FakeResponse] | None = None):
        self.responses = responses or [_FakeResponse(200)]
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, *, params=None, json=None):
        self.calls.append({"url": url, "params": params, "json": json})
        if self.responses:
            return self.responses.pop(0)
        return _FakeResponse(200)

    async def aclose(self):
        pass


class _FakeSink:
    name = "fake"

    def __init__(self):
        self.emitted: list[tuple[AnalyticsEvent, TenantContext | None]] = []

        # Pretend metrics container
        @dataclass
        class _M:
            success_total: int = 0
            failure_total: int = 0
            dropped_total: int = 0
            last_latency_ms: float = 0.0

        self.metrics = _M()

    async def emit(self, event, tenant=None):
        self.emitted.append((event, tenant))
        self.metrics.success_total += 1
        return SinkResult(ok=True, status_code=200)

    async def close(self):
        pass


@dataclass
class _FakeEnvelope:
    event_type: str = "app.Order.created"
    payload: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    key: str = ""

    @property
    def topic(self) -> str:
        parts = self.event_type.rsplit(".", 1)
        return parts[0] if len(parts) > 1 else self.event_type


# ---------------------------------------------------------------------------
# SinkRegistry
# ---------------------------------------------------------------------------


class TestSinkRegistry:
    def test_list_includes_ga4(self) -> None:
        assert "ga4_measurement_protocol" in list_sink_names()

    def test_factory_builds_sink(self) -> None:
        factory = get_sink_factory("ga4_measurement_protocol")
        assert factory is not None
        sink = factory({"measurement_id": "G-TEST"})
        assert sink.name == "ga4_measurement_protocol"
        assert sink.default_measurement_id == "G-TEST"  # type: ignore[attr-defined]

    def test_unknown_sink_returns_none(self) -> None:
        assert get_sink_factory("no-such") is None


# ---------------------------------------------------------------------------
# GA4 sink
# ---------------------------------------------------------------------------


class TestGA4Sink:
    @pytest.mark.asyncio
    async def test_missing_api_secret_returns_false_no_http(self, monkeypatch) -> None:
        monkeypatch.delenv("DAZZLE_GA4_API_SECRET", raising=False)
        sink = GA4MeasurementProtocolSink(default_measurement_id="G-X")
        fake = _FakeAsyncClient()
        sink._client = fake  # type: ignore[attr-defined]

        r = await sink.emit(AnalyticsEvent(name="dz_action", params={"x": 1}))
        assert r.ok is False
        assert "unset" in (r.error or "")
        assert fake.calls == []  # never called HTTP
        assert sink.metrics.failure_total == 1

    @pytest.mark.asyncio
    async def test_missing_measurement_id_returns_false(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_GA4_API_SECRET", "secret123")
        sink = GA4MeasurementProtocolSink(default_measurement_id=None)
        fake = _FakeAsyncClient()
        sink._client = fake  # type: ignore[attr-defined]

        r = await sink.emit(AnalyticsEvent(name="dz_action"))
        assert r.ok is False
        assert "measurement_id" in (r.error or "")
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_2xx_success_increments_counter(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_GA4_API_SECRET", "secret123")
        sink = GA4MeasurementProtocolSink(default_measurement_id="G-DEF")
        fake = _FakeAsyncClient([_FakeResponse(204)])
        sink._client = fake  # type: ignore[attr-defined]

        r = await sink.emit(AnalyticsEvent(name="dz_transition", params={"entity": "Order"}))
        assert r.ok is True
        assert r.status_code == 204
        assert sink.metrics.success_total == 1
        assert len(fake.calls) == 1

        # Payload shape
        call = fake.calls[0]
        assert call["params"]["measurement_id"] == "G-DEF"
        assert call["params"]["api_secret"] == "secret123"
        body = call["json"]
        assert body["events"][0]["name"] == "dz_transition"
        assert body["events"][0]["params"]["entity"] == "Order"
        assert "client_id" in body

    @pytest.mark.asyncio
    async def test_4xx_drops_no_retry(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_GA4_API_SECRET", "s")
        sink = GA4MeasurementProtocolSink(default_measurement_id="G-X")
        fake = _FakeAsyncClient([_FakeResponse(400, text="bad request")])
        sink._client = fake  # type: ignore[attr-defined]

        r = await sink.emit(AnalyticsEvent(name="dz_action"))
        assert r.ok is False
        assert r.status_code == 400
        assert sink.metrics.dropped_total == 1
        # Exactly one HTTP call — no retry for 4xx.
        assert len(fake.calls) == 1

    @pytest.mark.asyncio
    async def test_5xx_retries(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_GA4_API_SECRET", "s")
        sink = GA4MeasurementProtocolSink(
            default_measurement_id="G-X",
            backoff_schedule=(0.0, 0.0, 0.0),  # no delay in test
        )
        fake = _FakeAsyncClient([_FakeResponse(502), _FakeResponse(503), _FakeResponse(200)])
        sink._client = fake  # type: ignore[attr-defined]

        r = await sink.emit(AnalyticsEvent(name="dz_action"))
        assert r.ok is True
        assert r.status_code == 200
        assert len(fake.calls) == 3

    @pytest.mark.asyncio
    async def test_5xx_exhaust_retries(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_GA4_API_SECRET", "s")
        sink = GA4MeasurementProtocolSink(
            default_measurement_id="G-X",
            backoff_schedule=(0.0, 0.0, 0.0),
        )
        fake = _FakeAsyncClient([_FakeResponse(500), _FakeResponse(500), _FakeResponse(500)])
        sink._client = fake  # type: ignore[attr-defined]

        r = await sink.emit(AnalyticsEvent(name="dz_action"))
        assert r.ok is False
        assert sink.metrics.failure_total == 1
        assert len(fake.calls) == 3

    @pytest.mark.asyncio
    async def test_tenant_measurement_id_overrides_default(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_GA4_API_SECRET", "s")
        sink = GA4MeasurementProtocolSink(default_measurement_id="G-DEF")
        fake = _FakeAsyncClient([_FakeResponse(204)])
        sink._client = fake  # type: ignore[attr-defined]

        await sink.emit(
            AnalyticsEvent(name="dz_action"),
            TenantContext(
                tenant_slug="acme",
                analytics_config={"ga4_measurement_id": "G-ACME"},
            ),
        )
        assert fake.calls[0]["params"]["measurement_id"] == "G-ACME"

    @pytest.mark.asyncio
    async def test_params_stripped_of_non_primitives(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_GA4_API_SECRET", "s")
        sink = GA4MeasurementProtocolSink(default_measurement_id="G-X")
        fake = _FakeAsyncClient([_FakeResponse(204)])
        sink._client = fake  # type: ignore[attr-defined]

        await sink.emit(
            AnalyticsEvent(
                name="dz_action",
                params={"ok": 1, "also_ok": "hi", "nested": {"bad": 1}, "lst": [1, 2]},
            )
        )
        body_params = fake.calls[0]["json"]["events"][0]["params"]
        assert body_params == {"ok": 1, "also_ok": "hi"}


# ---------------------------------------------------------------------------
# Topic-glob matching
# ---------------------------------------------------------------------------


class TestTopicGlob:
    def test_exact_match(self) -> None:
        assert match_topic_glob("order.created", "order.created")
        assert not match_topic_glob("order.updated", "order.created")

    def test_single_star(self) -> None:
        assert match_topic_glob("audit.login", "audit.*")
        assert match_topic_glob("audit.logout", "audit.*")
        # single star does NOT span segments
        assert not match_topic_glob("audit.user.login", "audit.*")

    def test_double_star(self) -> None:
        assert match_topic_glob("audit.user.login", "audit.**")
        assert match_topic_glob("audit.user.profile.changed", "audit.**")
        assert match_topic_glob("audit.login", "audit.**")

    def test_wildcard_mid_segment(self) -> None:
        assert match_topic_glob("order.Pending.created", "order.*.created")
        assert not match_topic_glob("order.Pending.updated", "order.*.created")

    def test_bare_star(self) -> None:
        assert match_topic_glob("ping", "*")
        assert not match_topic_glob("ping.pong", "*")


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class TestAnalyticsBridge:
    @pytest.mark.asyncio
    async def test_accepts_only_matching_topic(self) -> None:
        sink = _FakeSink()
        bridge = AnalyticsBridge(sink=sink, bus_topics=["audit.*", "order.completed"])

        # matching
        await bridge.handle_envelope(_FakeEnvelope(event_type="audit.login"))
        assert len(sink.emitted) == 1

        # not matching
        await bridge.handle_envelope(_FakeEnvelope(event_type="unrelated.event"))
        assert len(sink.emitted) == 1  # unchanged

    @pytest.mark.asyncio
    async def test_disabled_gate_short_circuits(self, monkeypatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "dev")
        sink = _FakeSink()
        bridge = AnalyticsBridge(sink=sink, bus_topics=["**"])
        await bridge.handle_envelope(_FakeEnvelope(event_type="app.Order.created"))
        assert sink.emitted == []

    @pytest.mark.asyncio
    async def test_envelope_to_event_name(self) -> None:
        sink = _FakeSink()
        bridge = AnalyticsBridge(sink=sink, bus_topics=["app.**"])
        await bridge.handle_envelope(_FakeEnvelope(event_type="app.Order.created"))
        assert len(sink.emitted) == 1
        event, _ = sink.emitted[0]
        # Drops the leading app. prefix; joins remaining with underscore.
        assert event.name == "order_created"

    @pytest.mark.asyncio
    async def test_payload_primitives_pass_through(self) -> None:
        sink = _FakeSink()
        bridge = AnalyticsBridge(sink=sink, bus_topics=["**"])
        env = _FakeEnvelope(
            event_type="app.Order.completed",
            payload={"amount": 10.5, "currency": "USD", "nested": {}, "tags": []},
        )
        await bridge.handle_envelope(env)
        params = sink.emitted[0][0].params
        assert params["amount"] == 10.5
        assert params["currency"] == "USD"
        assert "nested" not in params
        assert "tags" not in params

    @pytest.mark.asyncio
    async def test_source_topic_recorded(self) -> None:
        sink = _FakeSink()
        bridge = AnalyticsBridge(sink=sink, bus_topics=["**"])
        await bridge.handle_envelope(_FakeEnvelope(event_type="audit.login"))
        event, _ = sink.emitted[0]
        assert event.source == "bus"
        # Bridge records the full event_type so users can route on it.
        assert event.topic == "audit.login"

    @pytest.mark.asyncio
    async def test_sink_errors_never_propagate(self) -> None:
        class _Breaking(_FakeSink):
            async def emit(self, event, tenant=None):
                raise RuntimeError("boom")

        bridge = AnalyticsBridge(sink=_Breaking(), bus_topics=["**"])
        # Should not raise.
        await bridge.handle_envelope(_FakeEnvelope(event_type="app.Order.created"))

    @pytest.mark.asyncio
    async def test_tenant_resolver_invoked(self) -> None:
        sink = _FakeSink()
        tenants = []

        def resolver(envelope):
            tenants.append(envelope.event_type)
            return TenantContext(tenant_slug="acme")

        bridge = AnalyticsBridge(sink=sink, bus_topics=["**"], tenant_resolver=resolver)
        await bridge.handle_envelope(_FakeEnvelope(event_type="app.X.y"))
        assert tenants == ["app.X.y"]
        assert sink.emitted[0][1].tenant_slug == "acme"


# ---------------------------------------------------------------------------
# build_bridge_from_spec
# ---------------------------------------------------------------------------


class TestBuildBridgeFromSpec:
    def test_none_spec_returns_none(self) -> None:
        assert build_bridge_from_spec(None) is None  # type: ignore[arg-type]

    def test_spec_without_server_side_returns_none(self) -> None:
        spec = AnalyticsSpec()
        assert build_bridge_from_spec(spec) is None

    def test_unknown_sink_returns_none(self) -> None:
        spec = AnalyticsSpec(
            server_side=AnalyticsServerSideSpec(sink="no_such_sink", bus_topics=["audit.*"])
        )
        assert build_bridge_from_spec(spec) is None

    def test_ga4_sink_builds_bridge(self) -> None:
        spec = AnalyticsSpec(
            server_side=AnalyticsServerSideSpec(
                sink="ga4_measurement_protocol",
                measurement_id="G-X",
                bus_topics=["audit.*"],
            )
        )
        bridge = build_bridge_from_spec(spec)
        assert bridge is not None
        assert isinstance(bridge.sink, GA4MeasurementProtocolSink)
        assert bridge.sink.default_measurement_id == "G-X"  # type: ignore[attr-defined]
        assert bridge.bus_topics == ["audit.*"]
