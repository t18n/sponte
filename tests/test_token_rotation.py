from ralph_focus.token_rotation import TokenRotationPolicy, rotation_policy_from_overrides


def test_warn_threshold_defaults_from_rotate_threshold() -> None:
    policy = TokenRotationPolicy(rotate_threshold=80_000, warn_threshold=0)
    assert policy.warn_threshold == 70_000


def test_rotation_policy_warns_before_rotate() -> None:
    policy = TokenRotationPolicy(rotate_threshold=80_000, warn_threshold=70_000)
    assert policy.classify(69_999) == "ok"
    assert policy.classify(70_000) == "warn"
    assert policy.classify(79_999) == "warn"
    assert policy.classify(80_000) == "rotate"


def test_rotation_policy_override_respects_cli_values() -> None:
    policy = rotation_policy_from_overrides(
        rotate_threshold=120_000,
        warn_threshold=90_000,
        default_rotate_threshold=80_000,
        default_warn_threshold=70_000,
    )
    assert policy.rotate_threshold == 120_000
    assert policy.warn_threshold == 90_000
