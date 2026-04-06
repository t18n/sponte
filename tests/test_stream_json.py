from ralph_focus.stream_json import usage_delta_from_stream_line


def test_usage_delta_from_stream_line_tracks_incremental_totals() -> None:
    previous: dict[str, int] = {}

    delta1, previous = usage_delta_from_stream_line(
        '{"type":"completion","usage":{"input_tokens":10,"output_tokens":4}}',
        previous,
    )
    delta2, previous = usage_delta_from_stream_line(
        '{"type":"completion","usage":{"input_tokens":15,"output_tokens":9}}',
        previous,
    )

    assert delta1 == {"input_tokens": 10, "output_tokens": 4}
    assert delta2 == {"input_tokens": 5, "output_tokens": 5}
    assert previous == {"input_tokens": 15, "output_tokens": 9}
