from config.defaults import NO_PROGRESS_LOOPS_MAX
from config.defaults import NO_PROGRESS_LOOPS_MAX
from ralph_focus.failure_detection import FailureKind, ProgressSnapshot, classify_agent_failure


def test_timeout_and_rate_limit_errors_are_transient() -> None:
    timeout = classify_agent_failure(
        "agent failed",
        "request timed out while waiting for the model backend",
        no_progress_streak=0,
    )
    rate_limited = classify_agent_failure(
        "agent failed",
        "HTTP 429 rate limit exceeded",
        no_progress_streak=0,
    )

    assert timeout.kind is FailureKind.TRANSIENT
    assert rate_limited.kind is FailureKind.TRANSIENT


def test_no_space_left_on_device_is_transient() -> None:
    result = classify_agent_failure(
        "agent failed",
        "OSError: [Errno 28] No space left on device",
        no_progress_streak=0,
    )

    assert result.kind is FailureKind.TRANSIENT


def test_repeated_no_progress_is_classified_as_gutter() -> None:
    result = classify_agent_failure(
        "agent produced no useful changes",
        "no files changed",
        no_progress_streak=NO_PROGRESS_LOOPS_MAX,
        before=ProgressSnapshot(pending_count=4, dirty=False, head="abc"),
        after=ProgressSnapshot(pending_count=4, dirty=False, head="abc"),
    )

    assert result.kind is FailureKind.GUTTER


def test_repeated_no_progress_uses_configured_threshold() -> None:
    result = classify_agent_failure(
        "agent produced no useful changes",
        "no files changed",
        no_progress_streak=NO_PROGRESS_LOOPS_MAX,
        before=ProgressSnapshot(pending_count=4, dirty=False, head="abc"),
        after=ProgressSnapshot(pending_count=4, dirty=False, head="abc"),
    )

    assert result.kind is FailureKind.GUTTER
