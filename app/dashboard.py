"""Runtime dashboard 6 panel, đọc `data/logs.jsonl` theo contract `config/dashboard.yaml`.

Không cần thư viện ngoài: tính số liệu theo từng phút trong cửa sổ `time_range_minutes`
rồi vẽ biểu đồ SVG. Mở tại `GET /dashboard` (tự refresh) hoặc xuất file bằng
`python -m app.dashboard`.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from . import logging_config
from .metrics import percentile

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "dashboard.yaml"
COLORS = ["#2563eb", "#f59e0b", "#dc2626", "#16a34a", "#7c3aed"]
Series = dict[str, list[float | None]]


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["dashboard"]


def load_events(log_path: Path, start: datetime) -> list[tuple[datetime, dict]]:
    if not log_path.exists():
        return []
    events = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
            ts = datetime.fromisoformat(str(record["ts"]).replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if ts >= start:
            events.append((ts, record))
    return events


def _bucketize(events: list[tuple[datetime, dict]], start: datetime, minutes: int) -> list[list[dict]]:
    buckets: list[list[dict]] = [[] for _ in range(minutes)]
    for ts, record in events:
        index = int((ts - start).total_seconds() // 60)
        if 0 <= index < minutes:
            buckets[index].append(record)
    return buckets


def _of(bucket: list[dict], event: str) -> list[dict]:
    return [r for r in bucket if r.get("event") == event]


def _values(records: list[dict], field: str) -> list[float]:
    return [r[field] for r in records if isinstance(r.get(field), (int, float))]


def _cumulative(values: list[float | None]) -> list[float | None]:
    """Cộng dồn theo phút; để trống (None) cho tới phút đầu tiên có dữ liệu."""
    total, started, out = 0.0, False, []
    for value in values:
        started = started or value is not None
        total += value or 0.0
        out.append(round(total, 6) if started else None)
    return out


def compute_panels(config: dict[str, Any], events: list[tuple[datetime, dict]], start: datetime) -> dict[str, dict]:
    minutes = int(config["time_range_minutes"])
    buckets = _bucketize(events, start, minutes)
    records = [r for _, r in events]
    sent = _of(records, "response_sent")
    received = _of(records, "request_received")
    failed = _of(records, "request_failed")

    def per_minute(fn) -> list[float | None]:
        return [fn(bucket) for bucket in buckets]

    def pct(field: str, p: int):
        return lambda b: percentile(_values(_of(b, "response_sent"), field), p) if _of(b, "response_sent") else None

    latency = _values(sent, "latency_ms")
    ttft = _values(sent, "ttft_ms")
    tool_flags = [r["tool_success"] for r in records if isinstance(r.get("tool_success"), bool)]
    cost_per_min = per_minute(lambda b: sum(_values(_of(b, "response_sent"), "cost_usd")) if _of(b, "response_sent") else None)
    tokens_in_min = per_minute(lambda b: sum(_values(_of(b, "response_sent"), "tokens_in")) if _of(b, "response_sent") else None)
    tokens_out_min = per_minute(lambda b: sum(_values(_of(b, "response_sent"), "tokens_out")) if _of(b, "response_sent") else None)
    quality = _values(sent, "quality_score")

    return {
        "latency": {
            "series": {
                "P50": per_minute(pct("latency_ms", 50)),
                "P95": per_minute(pct("latency_ms", 95)),
                "P99": per_minute(pct("latency_ms", 99)),
                "TTFT P95": per_minute(pct("ttft_ms", 95)),
            },
            "stats": {
                "p50": percentile(latency, 50),
                "p95": percentile(latency, 95),
                "p99": percentile(latency, 99),
                "ttft_p95": percentile(ttft, 95),
            },
        },
        "traffic": {
            "series": {"requests/min": per_minute(lambda b: float(len(_of(b, "request_received"))))},
            "bars": True,
            "stats": {"count": len(received), "rate_per_minute": round(len(received) / minutes, 2)},
        },
        "errors": {
            "series": {
                "error rate %": per_minute(
                    lambda b: round(len(_of(b, "request_failed")) / len(_of(b, "request_received")) * 100, 2)
                    if _of(b, "request_received") else None
                ),
                "retrieval success %": per_minute(
                    lambda b: round(
                        sum(1 for r in b if r.get("tool_success") is True)
                        / max(1, sum(1 for r in b if isinstance(r.get("tool_success"), bool))) * 100, 2
                    ) if any(isinstance(r.get("tool_success"), bool) for r in b) else None
                ),
            },
            "stats": {
                "error_rate_pct": round(len(failed) / len(received) * 100, 2) if received else 0.0,
                "count_by_value": dict(Counter(r.get("error_type", "unknown") for r in failed)),
                "tool_success_rate_pct": round(sum(tool_flags) / len(tool_flags) * 100, 2) if tool_flags else 100.0,
            },
        },
        "cost": {
            "series": {"cumulative USD": _cumulative(cost_per_min), "USD/min": cost_per_min},
            "stats": {"total": round(sum(_values(sent, "cost_usd")), 6), "sum_by_minute_max": round(max([c or 0 for c in cost_per_min] or [0]), 6)},
        },
        "tokens": {
            "series": {"cumulative input": _cumulative(tokens_in_min), "cumulative output": _cumulative(tokens_out_min)},
            "stats": {"sum_by_field": {"tokens_in": int(sum(_values(sent, "tokens_in"))), "tokens_out": int(sum(_values(sent, "tokens_out")))}},
        },
        "quality": {
            "series": {"mean quality": per_minute(lambda b: round(mean(_values(_of(b, "response_sent"), "quality_score")), 3) if _values(_of(b, "response_sent"), "quality_score") else None)},
            "stats": {"mean": round(mean(quality), 3) if quality else 0.0},
        },
    }


def _threshold_status(panel: dict, stats: dict) -> tuple[float | None, bool | None]:
    threshold = panel["threshold"]
    observed = stats.get(threshold["aggregation"])
    if isinstance(observed, dict):  # tokens: so sánh tổng lớn nhất trong các field
        observed = max(observed.values()) if observed else None
    if not isinstance(observed, (int, float)):
        return None, None
    ok = observed <= threshold["value"] if threshold["operator"] == "lte" else observed >= threshold["value"]
    return observed, ok


def svg_chart(series: Series, start: datetime, threshold: float, unit: str, bars: bool = False,
              width: int = 520, height: int = 220) -> str:
    left, right, top, bottom = 56, 12, 12, 30
    plot_w, plot_h = width - left - right, height - top - bottom
    n = max(len(values) for values in series.values())
    points = [v for values in series.values() for v in values if v is not None]
    y_max = max(points + [threshold, 0]) * 1.15 or 1.0
    x = lambda i: left + (i + 0.5) * plot_w / n
    y = lambda v: top + plot_h - (v / y_max) * plot_h
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img">',
             f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#f8fafc" stroke="#cbd5e1"/>']
    for frac in (0, 0.5, 1):
        value = y_max * frac
        parts.append(f'<text x="{left - 6}" y="{y(value) + 4:.1f}" font-size="10" text-anchor="end" fill="#475569">{value:,.4g}</text>')
    for i in range(0, n, 10):
        label = (start + timedelta(minutes=i)).strftime("%H:%M")
        parts.append(f'<text x="{x(i):.1f}" y="{height - 10}" font-size="10" text-anchor="middle" fill="#475569">{label}</text>')
    for color, (name, values) in zip(COLORS, series.items()):
        if bars:
            bar_w = max(2.0, plot_w / n * 0.7)
            for i, v in enumerate(values):
                if v:
                    parts.append(f'<rect x="{x(i) - bar_w / 2:.1f}" y="{y(v):.1f}" width="{bar_w:.1f}" height="{y(0) - y(v):.1f}" fill="{color}"/>')
            continue
        segment: list[str] = []
        for i, v in enumerate(values + [None]):
            if v is None:
                if len(segment) > 1:
                    parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(segment)}"/>')
                segment = []
                continue
            segment.append(f"{x(i):.1f},{y(v):.1f}")
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="{color}"/>')
    ty = y(threshold)
    parts.append(f'<line x1="{left}" x2="{left + plot_w}" y1="{ty:.1f}" y2="{ty:.1f}" stroke="#dc2626" stroke-dasharray="6 4" stroke-width="1.5"/>')
    parts.append(f'<text x="{left + plot_w - 4}" y="{ty - 4:.1f}" font-size="10" text-anchor="end" fill="#dc2626">threshold {threshold:g} {escape(unit)}</text>')
    parts.append("</svg>")
    legend = " ".join(f'<span style="color:{c}">&#9632; {escape(name)}</span>' for c, name in zip(COLORS, series))
    return "".join(parts) + f'<div class="legend">{legend}</div>'


def render_dashboard(now: datetime | None = None, log_path: Path | None = None,
                     config_path: Path = CONFIG_PATH) -> str:
    config = load_config(config_path)
    minutes = int(config["time_range_minutes"])
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(minutes=minutes - 1)).replace(second=0, microsecond=0)
    events = load_events(log_path or logging_config.LOG_PATH, start)
    data = compute_panels(config, events, start)

    cards = []
    for panel in config["panels"]:
        result = data[panel["id"]]
        threshold = panel["threshold"]
        observed, ok = _threshold_status(panel, result["stats"])
        op = "≤" if threshold["operator"] == "lte" else "≥"
        badge = "no data" if ok is None else ("OK" if ok else "BREACH")
        badge_class = "nodata" if ok is None else ("ok" if ok else "breach")
        stats = ", ".join(f"{escape(k)}={escape(json.dumps(v, ensure_ascii=False))}" for k, v in result["stats"].items())
        cards.append(
            f'<section class="card"><h2>{escape(panel["title"])}</h2>'
            f'<p class="meta">unit: <b>{escape(panel["unit"])}</b> · range: last {minutes} min · '
            f'threshold: {escape(threshold["aggregation"])} {op} {threshold["value"]} '
            f'<span class="badge {badge_class}">{badge}{"" if observed is None else f" ({observed:g})"}</span></p>'
            f'{svg_chart(result["series"], start, float(threshold["value"]), panel["unit"], result.get("bars", False))}'
            f'<p class="stats">{stats}</p></section>'
        )

    total = len([1 for _, r in events if r.get("event") == "request_received"])
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="{int(config["refresh_seconds"])}">
<title>{escape(config["title"])}</title>
<style>
body{{font-family:system-ui,Segoe UI,sans-serif;margin:16px;background:#fff;color:#0f172a}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#475569;margin:0 0 12px;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:12px}}
.card{{border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px}} h2{{font-size:15px;margin:0 0 4px}}
.meta,.stats,.legend{{font-size:12px;color:#334155;margin:4px 0}} .legend span{{margin-right:10px}}
.badge{{padding:1px 6px;border-radius:4px;font-weight:600}} .ok{{background:#dcfce7;color:#166534}}
.breach{{background:#fee2e2;color:#991b1b}} .nodata{{background:#e2e8f0;color:#334155}}
</style></head><body>
<h1>{escape(config["title"])}</h1>
<p class="sub">Source: {escape(str(log_path or logging_config.LOG_PATH))} · window {start:%Y-%m-%d %H:%M}–{now:%H:%M} UTC ·
{total} requests · auto-refresh {int(config["refresh_seconds"])}s</p>
<div class="grid">{"".join(cards)}</div></body></html>"""


if __name__ == "__main__":
    out = Path("data/dashboard.html")
    out.write_text(render_dashboard(), encoding="utf-8")
    print(f"Wrote {out}")
