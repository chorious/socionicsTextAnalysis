"""Commit F: indicator hit rate metric."""
from __future__ import annotations


def test_hit_rate_mixed(analyzer_heuristic):
    quotes = [
        {"indicator": "IND TM-A"},
        {"indicator": "IND ST-A"},
        {"indicator": "IND NR-D"},
        {"indicator": "IND VT-A"},
        {"indicator": "IND HD-B"},
        {"indicator": ""},
        {"indicator": "not-a-real-code"},
        {"indicator": "another-illegal"},
    ]
    assert analyzer_heuristic._indicator_hit_rate(quotes) == 0.625


def test_hit_rate_empty(analyzer_heuristic):
    assert analyzer_heuristic._indicator_hit_rate([]) == 0.0


def test_hit_rate_all_legal(analyzer_heuristic):
    quotes = [{"indicator": "IND TM-A"}, {"indicator": "IND ST-A"}]
    assert analyzer_heuristic._indicator_hit_rate(quotes) == 1.0


def test_hit_rate_all_illegal(analyzer_heuristic):
    quotes = [{"indicator": ""}, {"indicator": "garbage"}]
    assert analyzer_heuristic._indicator_hit_rate(quotes) == 0.0


def test_result_preprocess_carries_hit_rate(analyzer_heuristic, sample_text):
    """End-to-end: result.preprocess.indicator_hit_rate is present and reflects
    the indicator quality of the extracted quotes."""
    result = analyzer_heuristic.analyze(sample_text, case_id="hit-rate-smoke")
    assert "indicator_hit_rate" in result["preprocess"]
    rate = result["preprocess"]["indicator_hit_rate"]
    assert isinstance(rate, float)
    assert 0.0 <= rate <= 1.0
