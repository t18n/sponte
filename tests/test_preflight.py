from pathlib import Path


def test_collect_preflight_rows_uses_harness_availability(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus import preflight
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=False, problems=("missing cursor-agent",))

    monkeypatch.setattr(preflight, "git_toplevel", lambda: tmp_path)
    monkeypatch.setattr(preflight, "_agent_executable_path", lambda _agent_id: "/bin/cursor-agent")
    monkeypatch.setattr(preflight.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        preflight,
        "get_strategy",
        lambda _name: (_ for _ in ()).throw(AssertionError("preflight should use get_harness")),
        raising=False,
    )
    monkeypatch.setattr(preflight, "get_harness", lambda name: _Harness(), raising=False)

    rows = preflight._collect_preflight_rows(agent="cursor")

    assert ("Agent CLI (cursor)", "fail", "missing cursor-agent") in rows


def test_collect_preflight_rows_treats_unavailable_harness_without_problems_as_failure(
    monkeypatch, tmp_path: Path
) -> None:
    from ralph_focus import preflight
    from ralph_focus.contracts import AvailabilityReport, HarnessCapabilities

    class _Harness:
        id = "cursor"
        display_name = "Cursor"
        capabilities = HarnessCapabilities()

        def availability(self) -> AvailabilityReport:
            return AvailabilityReport(available=False, problems=())

    monkeypatch.setattr(preflight, "git_toplevel", lambda: tmp_path)
    monkeypatch.setattr(preflight, "_agent_executable_path", lambda _agent_id: "/bin/cursor-agent")
    monkeypatch.setattr(preflight.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(preflight, "get_harness", lambda name: _Harness(), raising=False)

    rows = preflight._collect_preflight_rows(agent="cursor")

    assert ("Agent CLI (cursor)", "fail", "reported unavailable") in rows
