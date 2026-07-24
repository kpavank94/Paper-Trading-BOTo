"""Regression tests for background command lifecycle reporting."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

import pytest

from src.tools import background_tools
from src.tools.background_tools import BackgroundManager


def _execute(manager: BackgroundManager, task_id: str, command: str) -> dict:
    manager.tasks[task_id] = {
        "status": "running",
        "result": None,
        "command": command,
        "exit_code": None,
    }
    manager._execute(task_id, command)
    return manager.tasks[task_id]


def test_nonzero_exit_is_reported_as_error() -> None:
    manager = BackgroundManager()
    command = f'"{sys.executable}" -c "import sys; print(\'failed output\'); sys.exit(7)"'

    task = _execute(manager, "failed", command)

    assert task["status"] == "error"
    assert task["exit_code"] == 7
    assert "failed output" in task["result"]
    checked = json.loads(manager.check("failed"))
    assert checked["status"] == "error"
    assert checked["exit_code"] == 7
    assert manager.drain_notifications() == [
        {
            "task_id": "failed",
            "status": "error",
            "command": command[:80],
            "result": "failed output",
            "exit_code": 7,
        }
    ]


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group regression")
def test_timeout_kills_descendant_and_reaps_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_marker = tmp_path / "child-started"
    orphan_marker = tmp_path / "orphan-wrote-after-timeout"
    child_code = (
        "import time; from pathlib import Path; "
        f"Path({str(started_marker)!r}).write_text('started', encoding='utf-8'); "
        "time.sleep(1.5); "
        f"Path({str(orphan_marker)!r}).write_text('orphan', encoding='utf-8')"
    )
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(child_code)} & wait"
    processes: list[background_tools.subprocess.Popen[str]] = []
    real_popen = background_tools.subprocess.Popen

    def tracked_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(background_tools, "_COMMAND_TIMEOUT_SECONDS", 0.8)
    monkeypatch.setattr(background_tools, "_TERMINATION_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(background_tools.subprocess, "Popen", tracked_popen)

    manager = BackgroundManager()
    task = _execute(manager, "timeout", command)

    assert started_marker.exists()
    assert task["status"] == "timeout"
    assert processes[0].poll() is not None
    time.sleep(1.0)
    assert not orphan_marker.exists()
