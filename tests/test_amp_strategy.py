from pathlib import Path


def test_amp_strategy_defaults_to_least_privilege(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus.strategies.amp import AmpStrategy

    seen: dict[str, object] = {}

    class _Result:
        exit_code = 0
        retryable = False
        cancellation_reason = ""

    def fake_run(args: list[str], *, cwd: Path, log_file: Path, tee: bool, watchdog, event_callback):
        seen["args"] = args
        seen["cwd"] = cwd
        seen["log_file"] = log_file
        seen["tee"] = tee
        seen["watchdog"] = watchdog
        seen["event_callback"] = event_callback
        return _Result()

    monkeypatch.delenv("RALPH_AMP_DANGEROUSLY_ALLOW_ALL", raising=False)
    monkeypatch.setattr("ralph_focus.strategies.amp.run_subprocess_streaming", fake_run)

    result = AmpStrategy().run(
        tmp_path,
        "sonnet",
        "do the thing",
        tmp_path / "amp.log",
        use_stream_json=False,
        tee=False,
        metrics_out=None,
        watchdog=None,
        event_callback=None,
    )

    assert result.exit_code == 0
    assert result.usage == {}
    assert "--dangerously-allow-all" not in seen["args"]
