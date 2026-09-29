from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.dashboard import CONFIG_PATH, compute_panels, load_config, load_events, render_dashboard

NOW = datetime(2026, 9, 29, 8, 0, 30, tzinfo=timezone.utc)


def _write_logs(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _request(minutes_ago: int, latency: int, *, failed: bool = False) -> list[dict]:
    ts = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    base = {"ts": ts, "level": "info", "service": "api", "correlation_id": f"req-{minutes_ago:08x}"}
    received = {**base, "event": "request_received"}
    if failed:
        return [received, {**base, "level": "error", "event": "request_failed", "error_type": "RuntimeError",
                           "tool_name": "retrieval", "tool_success": False}]
    return [received, {**base, "event": "response_sent", "latency_ms": latency, "ttft_ms": 50,
                       "tokens_in": 30, "tokens_out": 100, "cost_usd": 0.0016, "quality_score": 0.8,
                       "tool_name": "retrieval", "tool_success": True}]


def test_dashboard_renders_six_panels_with_units_range_and_thresholds(tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    _write_logs(log_path, [r for m in (1, 2, 3) for r in _request(m, 400)])

    html = render_dashboard(now=NOW, log_path=log_path)

    config = load_config()
    for panel in config["panels"]:
        assert panel["title"] in html
        assert f"unit: <b>{panel['unit']}</b>" in html
    assert html.count("last 60 min") == 6
    assert html.count("stroke-dasharray") == 6  # một đường threshold/SLO cho mỗi panel
    assert 'http-equiv="refresh" content="30"' in html
    assert "3 requests" in html


def test_dashboard_ignores_events_older_than_time_range(tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    _write_logs(log_path, _request(90, 400) + _request(5, 400))

    start = NOW - timedelta(minutes=59)
    events = load_events(log_path, start)

    assert {r["correlation_id"] for _, r in events} == {"req-00000005"}


def test_errors_panel_flags_breach_and_retrieval_success(tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    _write_logs(log_path, _request(3, 400) + _request(2, 400, failed=True))

    config = load_config(CONFIG_PATH)
    start = (NOW - timedelta(minutes=59)).replace(second=0, microsecond=0)
    stats = compute_panels(config, load_events(log_path, start), start)["errors"]["stats"]

    assert stats["error_rate_pct"] == 50.0
    assert stats["tool_success_rate_pct"] == 50.0
    assert stats["count_by_value"] == {"RuntimeError": 1}
    assert "BREACH" in render_dashboard(now=NOW, log_path=log_path)


def test_latency_panel_uses_percentiles_and_ttft(tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    _write_logs(log_path, [r for i, lat in enumerate([100, 200, 300, 4000]) for r in _request(i + 1, lat)])

    config = load_config()
    start = (NOW - timedelta(minutes=59)).replace(second=0, microsecond=0)
    stats = compute_panels(config, load_events(log_path, start), start)["latency"]["stats"]

    assert stats["p50"] == 200
    assert stats["p99"] == 4000
    assert stats["ttft_p95"] == 50
