"""Trace rendering and persistence."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .schema import TraceEvent


def render_trace(events: Iterable[TraceEvent]) -> str:
    lines: list[str] = []
    for event in events:
        status = "ok" if event.ok else "error"
        if event.ok is None:
            status = "info"
        line = f"[{event.step}] {status}"
        if event.tool:
            line += f" {event.tool}"
        if event.reason:
            line += f" reason={event.reason}"
        if event.top_ids:
            line += f" ids={','.join(event.top_ids)}"
        line += f" {event.latency_ms:.1f}ms"
        if event.decision_summary:
            line += f" | {event.decision_summary}"
        if event.hint:
            line += f" | hint={event.hint}"
        lines.append(line)
    return "\n".join(lines)


def write_trace_jsonl(events: Iterable[TraceEvent], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
