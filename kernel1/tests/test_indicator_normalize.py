"""Indicator whitelist + signal-based inference (Commit C)."""
from __future__ import annotations

from kernel1.core import IND_PROFILES


def test_legal_indicator_preserved(analyzer_heuristic):
    out = analyzer_heuristic._resolve_indicator({"indicator": "IND TM-A"})
    assert out == "IND TM-A"


def test_illegal_indicator_inferred_from_signals(analyzer_heuristic):
    item = {
        "indicator": "显性/感觉",
        "dimension_hint": "3D",
        "strength_signal": "strong",
        "valued_signal": "valued",
        "mental_signal": "mental",
    }
    out = analyzer_heuristic._resolve_indicator(item)
    assert out == "IND ST-A"


def test_illegal_indicator_no_signals_falls_to_empty(analyzer_heuristic):
    item = {"indicator": "strong_logic"}
    out = analyzer_heuristic._resolve_indicator(item)
    assert out == ""


def test_normalize_replays_qa_smoke(analyzer_heuristic, qa_smoke_extraction):
    """Replay the canonical QA smoke evidence chain: every illegal indicator
    (e.g. '显性/感觉') must be normalized to a legal IND code or empty string."""
    raw = {
        "quotes": qa_smoke_extraction,
        "dichotomy_signals": {},
        "conflicts": [],
        "insufficiency": [],
        "laning_signals": {},
    }
    normalized = analyzer_heuristic._normalize_extraction(raw)
    for q in normalized["quotes"]:
        ind = q["indicator"]
        assert ind == "" or ind in IND_PROFILES, f"unexpected indicator: {ind}"


def test_normalize_replays_qa_smoke_recovers_xianxing(analyzer_heuristic, qa_smoke_extraction):
    """The two '显性/感觉' rows in edited-qa-smoke-001 should be recovered to a legal IND."""
    raw = {
        "quotes": qa_smoke_extraction,
        "dichotomy_signals": {},
        "conflicts": [],
        "insufficiency": [],
        "laning_signals": {},
    }
    normalized = analyzer_heuristic._normalize_extraction(raw)
    recovered = [
        q for q in normalized["quotes"]
        if "舒适" in q["quote"] or "调整环境" in q["quote"]
    ]
    assert recovered, "expected to find the two Si '显性/感觉' rows"
    for q in recovered:
        assert q["indicator"] in IND_PROFILES, \
            f"row {q['quote']!r} still has illegal indicator {q['indicator']!r}"
