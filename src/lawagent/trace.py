"""Trace rendering and persistence."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .schema import RunMeta, RunResult, TraceEvent


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


def build_run_meta(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    data_path: str | Path,
    started_at: datetime,
) -> RunMeta:
    """Collect reproducibility metadata without requiring a Git repository."""

    target = Path(data_path)
    data_sha256 = ""
    if target.exists():
        data_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()

    git_commit = ""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if completed.returncode == 0:
            git_commit = completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    git_dirty = False
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        git_dirty = completed.returncode == 0 and bool(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass

    return RunMeta(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        data_path=str(target.resolve()),
        data_sha256=data_sha256,
        git_commit=git_commit,
        git_dirty=git_dirty,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def write_run_json(result: RunResult, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
