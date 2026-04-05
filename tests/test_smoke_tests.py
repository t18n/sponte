from ralph_focus import smoke_tests


def test_smoke_checks_run_cleanly() -> None:
    smoke_tests.run_all()


def test_smoke_checks_include_contract_boundary(monkeypatch) -> None:
    called: list[bool] = []

    monkeypatch.setattr(smoke_tests, "_test_contracts_boundary", lambda: called.append(True), raising=False)

    smoke_tests.run_all()

    assert called == [True]
