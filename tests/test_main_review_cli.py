from __future__ import annotations

import sys
from pathlib import Path

import pytest

import main
import core.review as review_mod


class _DummyRegistry:
    def close(self) -> None:
        return None


class _FakeConfig:
    def __init__(self, config_path: str = "config.yaml", profile_override: str | None = None):
        self.profile = profile_override or "dev"
        self.config_path = Path(config_path).resolve()
        self.log_level = "INFO"

    def get_path(self, key: str) -> str:
        if key == "outbox":
            return "/tmp/outbox"
        if key == "temp":
            return "/tmp/temp"
        return "/tmp"


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "Config", _FakeConfig)
    monkeypatch.setattr(main, "set_config", lambda _cfg: None)
    monkeypatch.setattr(main, "setup_logging", lambda _level="INFO": None)
    monkeypatch.setattr(main, "setup_tracing", lambda service_name=None: None)
    monkeypatch.setattr(main, "open_registry", lambda _cfg: _DummyRegistry())


def test_review_queue_mode_does_not_require_video(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(review_mod, "list_review_queue", lambda _registry: [])
    monkeypatch.setattr(sys, "argv", ["main.py", "--mode", "review", "--review-action", "queue"])

    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0


def test_review_reject_action_runs_without_video(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime(monkeypatch)
    monkeypatch.setattr(
        review_mod,
        "reject_review_task",
        lambda _registry, task_id, reviewer_notes=None: {"task_id": task_id, "status": "rejected"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--mode", "review", "--review-action", "reject", "--task-id", "9"],
    )

    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0
