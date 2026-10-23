from build_index_history import build_index_history_payload


def _rows(closes, start=1):
    return [{"date": f"2026-01-{start + i:02d}", "adjusted_close": close} for i, close in enumerate(closes)]


def test_aligns_every_proxy_to_the_calendar_symbol_and_never_fills_gaps():
    payload = build_index_history_payload({
        "SPY": _rows([100, 101, 102, 103]),
        "AGG": _rows([50, 51], start=3),
    }, generated_at="2026-01-05T22:00:00+00:00")
    assert payload["as_of"] == "2026-01-04"
    assert payload["dates"] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    assert payload["symbols"]["SPY"]["closes"] == [100, 101, 102, 103]
    assert payload["symbols"]["AGG"]["closes"] == [None, None, 50, 51]


def test_drops_a_proxy_without_two_usable_closes():
    payload = build_index_history_payload({"SPY": _rows([100, 101, 102]), "MUB": _rows([40])})
    assert "MUB" not in payload["symbols"]


def test_no_calendar_history_yields_no_payload():
    assert build_index_history_payload({"AGG": _rows([1, 2, 3])}) is None


def test_trims_to_the_requested_observation_count():
    payload = build_index_history_payload({"SPY": _rows(list(range(10, 20)))}, observations=3)
    assert payload["symbols"]["SPY"]["closes"] == [17, 18, 19]
