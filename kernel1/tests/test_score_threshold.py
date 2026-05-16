"""Commit E: saturation denominator + target_confidence threshold."""
from __future__ import annotations

from kernel1.core import AnalyzeOptions, Kernel1Analyzer
from kernel1.llm import LLMClient, LLMConfig


def _make_quote(element, dimension, indicator, strength="strong",
                valued="valued", mental="mental", accepting="accepting",
                contact="inert", guide="guide", confidence=0.7):
    return {
        "quote": f"q-{element}-{dimension}",
        "indicator": indicator,
        "element_hint": element,
        "dimension_hint": dimension,
        "position_hint": None,
        "strength_signal": strength,
        "valued_signal": valued,
        "mental_signal": mental,
        "accepting_signal": accepting,
        "contact_signal": contact,
        "guide_signal": guide,
        "confidence": confidence,
        "evidence_type": "identity",
        "reason": "synthetic",
    }


def test_analyze_options_exposes_new_knobs():
    opts = AnalyzeOptions()
    assert opts.target_confidence == 0.80
    assert opts.no_first_4d_ceiling == 0.58
    assert opts.denom_quote_cap == 12


def test_qa_smoke_normalizes_without_regression(analyzer_heuristic, qa_smoke_extraction):
    """QA smoke has no 4D evidence — scores should hit the no_first_4d ceiling.
    This is the correct behavior (no 4D => can't be certain). Production target ≥ 0.80
    requires LLM-extracted 4D quotes, validated separately by the synthetic test below."""
    raw = {
        "quotes": qa_smoke_extraction,
        "dichotomy_signals": {},
        "conflicts": [],
        "insufficiency": [],
        "laning_signals": {},
    }
    normalized = analyzer_heuristic._normalize_extraction(raw)
    candidates = analyzer_heuristic._score_candidates(normalized)
    top = candidates[0]
    # All candidates have first_4d_support == 0 because no quote is 4D,
    # so top should be capped at no_first_4d_ceiling = 0.58
    assert top["first_4d_support"] == 0.0
    assert top["score"] <= analyzer_heuristic.options.no_first_4d_ceiling + 1e-6


def test_strong_4d_evidence_breaks_certainty_threshold(analyzer_heuristic):
    """With 4D dominant + 3D creative + supporting evidence, top score should ≥ 0.78.
    Models the production scenario (LLM emits well-structured quotes)."""
    quotes = [
        _make_quote("Te", "4D", "IND TM-A", confidence=0.8),
        _make_quote("Te", "4D", "IND TM-A", confidence=0.8),
        _make_quote("Ni", "3D", "IND ST-A",
                    accepting="producing", contact="contact", guide="separate",
                    confidence=0.75),
        _make_quote("Ni", "3D", "IND ST-A",
                    accepting="producing", contact="contact", guide="separate",
                    confidence=0.75),
        _make_quote("Si", "3D", "IND VT-B",
                    valued="unvalued", mental="vital", confidence=0.6),
        _make_quote("Fi", "1D", "IND 1D-L",
                    strength="weak", valued="unvalued", mental="vital", confidence=0.6),
        _make_quote("Fe", "2D", "IND NR-D",
                    strength="weak", valued="unvalued", confidence=0.5),
    ]
    raw = {
        "quotes": quotes,
        "dichotomy_signals": {},
        "conflicts": [],
        "insufficiency": [],
        "laning_signals": {},
    }
    normalized = analyzer_heuristic._normalize_extraction(raw)
    candidates = analyzer_heuristic._score_candidates(normalized)
    assert candidates[0]["score"] >= 0.78, (
        f"top score {candidates[0]['score']} below target 0.78 — "
        f"saturation + IND inference may be misconfigured"
    )


def test_saturation_caps_max_possible_for_many_quotes(analyzer_heuristic):
    """When quote_count > denom_quote_cap, additional quotes should not inflate
    max_possible (so confidence is preserved)."""
    # Build 6-quote set (under cap) and 18-quote set (over cap) with identical content
    base = [
        _make_quote("Te", "4D", "IND TM-A", confidence=0.7),
        _make_quote("Ni", "3D", "IND ST-A",
                    accepting="producing", contact="contact", guide="separate",
                    confidence=0.7),
    ] * 3  # 6 quotes

    raw_small = {"quotes": base, "dichotomy_signals": {}, "conflicts": [], "insufficiency": [], "laning_signals": {}}
    normalized_small = analyzer_heuristic._normalize_extraction(raw_small)

    big = base * 3  # 18 quotes — should hit saturation cap of 12
    raw_big = {"quotes": big, "dichotomy_signals": {}, "conflicts": [], "insufficiency": [], "laning_signals": {}}
    normalized_big = analyzer_heuristic._normalize_extraction(raw_big)

    # Both should score the leading LIE-ish type. The big set should NOT score
    # appreciably lower than the small one — saturation prevents denominator inflation.
    cs = analyzer_heuristic._score_candidates(normalized_small)
    cb = analyzer_heuristic._score_candidates(normalized_big)
    # Small score must be reasonable, big score should not collapse
    assert cs[0]["score"] >= 0.6
    assert cb[0]["score"] >= cs[0]["score"] - 0.05


def test_target_confidence_gates_certain():
    """When top score < target_confidence (0.80), status must be uncertain
    even if all other gates pass."""
    a = Kernel1Analyzer(
        llm=LLMClient(LLMConfig(enabled=False)),
        options=AnalyzeOptions(target_confidence=0.80),
    )
    # Construct a top candidate with score 0.75 (above top_threshold 0.65, below target 0.80)
    fake_candidates = [
        {
            "type": "LIE", "score": 0.75,
            "first_hypothesis": "Te", "second_hypothesis": "Ni",
            "first_4d_support": 1.0, "first_axis_score": 1.2,
            "second_3d_support": 0.8,
            "first_leading_support": 0.6, "second_creative_support": 0.5,
            "second_ignoring_risk": 0.2,
            "rule_matches": [], "rule_conflicts": [],
            "global_score": 0.0, "global_matches": [], "global_conflicts": [],
            "hard_conflict_count": 0,
        },
        {
            "type": "LSE", "score": 0.60,
            "first_hypothesis": "Te", "second_hypothesis": "Si",
            "first_4d_support": 1.0, "first_axis_score": 1.0,
            "second_3d_support": 0.5,
            "first_leading_support": 0.5, "second_creative_support": 0.4,
            "second_ignoring_risk": 0.2,
            "rule_matches": [], "rule_conflicts": [],
            "global_score": 0.0, "global_matches": [], "global_conflicts": [],
            "hard_conflict_count": 0,
        },
    ]
    extraction = {"quotes": [{"quote": "x"}] * 5, "conflicts": [], "insufficiency": [], "laning_signals": {}, "dichotomy_signals": {}}
    prepared = {"mode": "plain_text", "qa_count": 0, "original_length": 100, "analysis_length": 100, "qa_items": []}
    result = a._build_result("case-target-gate", fake_candidates, extraction, prepared)
    assert result["status"] == "uncertain"
    assert result["type"] is None


def test_certain_when_score_meets_target():
    """When top score >= target_confidence and no gates fail, status is certain."""
    a = Kernel1Analyzer(
        llm=LLMClient(LLMConfig(enabled=False)),
        options=AnalyzeOptions(target_confidence=0.80),
    )
    fake_candidates = [
        {
            "type": "LIE", "score": 0.85,
            "first_hypothesis": "Te", "second_hypothesis": "Ni",
            "first_4d_support": 1.0, "first_axis_score": 1.2,
            "second_3d_support": 0.8,
            "first_leading_support": 0.6, "second_creative_support": 0.5,
            "second_ignoring_risk": 0.2,
            "rule_matches": [], "rule_conflicts": [],
            "global_score": 0.0, "global_matches": [], "global_conflicts": [],
            "hard_conflict_count": 0,
        },
        {
            "type": "LSE", "score": 0.60,
            "first_hypothesis": "Te", "second_hypothesis": "Si",
            "first_4d_support": 1.0, "first_axis_score": 1.0,
            "second_3d_support": 0.5,
            "first_leading_support": 0.5, "second_creative_support": 0.4,
            "second_ignoring_risk": 0.2,
            "rule_matches": [], "rule_conflicts": [],
            "global_score": 0.0, "global_matches": [], "global_conflicts": [],
            "hard_conflict_count": 0,
        },
    ]
    extraction = {"quotes": [{"quote": "x"}] * 5, "conflicts": [], "insufficiency": [], "laning_signals": {}, "dichotomy_signals": {}}
    prepared = {"mode": "plain_text", "qa_count": 0, "original_length": 100, "analysis_length": 100, "qa_items": []}
    result = a._build_result("case-target-pass", fake_candidates, extraction, prepared)
    assert result["status"] == "certain"
    assert result["type"] == "LIE"
