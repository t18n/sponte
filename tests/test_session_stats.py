from ralph_focus.session_stats import SessionStats


def test_total_tokens_prefers_explicit_step_total() -> None:
    stats = SessionStats()
    stats.add_tokens({"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
    assert stats.total_tokens() == 150


def test_total_tokens_falls_back_to_component_sum() -> None:
    stats = SessionStats()
    stats.add_tokens({"input_tokens": 100, "output_tokens": 50})
    assert stats.total_tokens() == 150


def test_total_tokens_accepts_lone_total_field() -> None:
    stats = SessionStats()
    stats.add_tokens({"total": 150})
    assert stats.total_tokens() == 150


def test_rotation_tokens_ignore_cache_reads_when_components_present() -> None:
    stats = SessionStats()
    stats.add_tokens(
        {
            "inputTokens": 100,
            "outputTokens": 50,
            "cacheReadTokens": 10_000,
            "cacheWriteTokens": 500,
            "totalTokens": 10_650,
        }
    )
    assert stats.rotation_tokens() == 150
