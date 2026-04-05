from pathlib import Path


def test_amp_strategy_defaults_to_least_privilege(monkeypatch, tmp_path: Path) -> None:
    from ralph_focus.strategies.amp import AmpStrategy

    seen: dict[str, object] = {}

    def fake_run(args: list[str], *, cwd: Path, capture_output: bool, text: bool):
        seen["args"] = args
        seen["cwd"] = cwd
        seen["capture_output"] = capture_output
        seen["text"] = text

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Completed()

    monkeypatch.delenv("RALPH_AMP_DANGEROUSLY_ALLOW_ALL", raising=False)
    monkeypatch.setattr("ralph_focus.strategies.amp.subprocess.run", fake_run)

    rc, usage = AmpStrategy().run(
        tmp_path,
        "sonnet",
        "do the thing",
        tmp_path / "amp.log",
        use_stream_json=False,
        tee=False,
        metrics_out=None,
    )

    assert rc == 0
    assert usage == {}
    assert "--dangerously-allow-all" not in seen["args"]
