"""Smoke test: end-to-end analyze with heuristic extractor."""
from __future__ import annotations


def test_analyze_smoke(analyzer_heuristic, sample_text):
    result = analyzer_heuristic.analyze(sample_text, case_id="smoke-test")
    assert isinstance(result, dict)
    for key in ("case_id", "status", "candidates", "report"):
        assert key in result, f"missing key: {key}"
    assert result["case_id"] == "smoke-test"
    assert result["status"] in {"certain", "uncertain", "clarifying", "rejected"}
    assert isinstance(result["candidates"], list)
    assert len(result["candidates"]) <= 3
