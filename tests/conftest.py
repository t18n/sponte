"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_sponte_runtime_data_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid host env leaking ``SPONTE_RUNTIME_DATA_IN_WORKSPACE`` into path resolution tests."""
    monkeypatch.delenv("SPONTE_RUNTIME_DATA_IN_WORKSPACE", raising=False)
