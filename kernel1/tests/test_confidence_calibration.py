"""v0.10 confidence calibration regression tests.

Fixtures `web-1778907758325.json` and `web-1778908013096.json` 是 5/16 出问题的两次 run
(Case A: status=certain + arbitration 覆盖 Top-1 / Case B: confidence=1.0 + type=null)。
通过把它们的 evidence_chain + 算法层信号灌回 _build_result(不调 LLM),验证 v0.10
calibration 把 confidence 强降 + saturation_event 触发 + algorithm_top 不再被覆盖。
"""
from __future__ import annotations

import json
from pathlib import Path

from kernel1.core import AnalyzeOptions, Kernel1Analyzer
from kernel1.llm import LLMClient, LLMConfig


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "outputs"
CASE_A = FIXTURE_DIR / "web-1778907758325.json"  # 1.0/1.0/0.77 Top-2 撞顶
CASE_B = FIXTURE_DIR / "web-1778908013096.json"  # 1.0/1.0/1.0 Top-3 撞顶


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rebuild(analyzer: Kernel1Analyzer, fixture: dict) -> dict:
    """用 fixture 里的 evidence_chain 重打分,直接喂 _build_result,不跑 LLM。"""
    extraction = {
        "quotes": fixture["evidence_chain"],
        "conflicts": fixture.get("conflicts", []),
        "insufficiency": fixture.get("insufficiency", []),
        "dichotomy_signals": fixture.get("dichotomy_signals", {}),
        "laning_signals": fixture.get("laning_signals", {}),
        "_source": fixture.get("extraction_source", "unknown"),
        "_indicator_hit_rate": fixture.get("preprocess", {}).get("indicator_hit_rate", 0.0),
    }
    candidates = analyzer._score_candidates(extraction)
    prepared = {
        "mode": fixture["preprocess"]["mode"],
        "qa_count": fixture["preprocess"]["qa_count"],
        "original_length": fixture["preprocess"]["original_length"],
        "analysis_length": fixture["preprocess"]["analysis_length"],
        "qa_items": fixture["preprocess"].get("qa_items", []),
        "source": fixture["preprocess"].get("source", "raw_text"),
    }
    return analyzer._build_result(fixture["case_id"], candidates, extraction, prepared)


def _make_analyzer() -> Kernel1Analyzer:
    return Kernel1Analyzer(llm=LLMClient(LLMConfig(enabled=False)))


def test_case_b_full_collision_confidence_capped():
    """1.0/1.0/1.0 撞顶 case:confidence ≤ 0.5 且触发 top_band_collision。"""
    fixture = _load_fixture(CASE_B)
    analyzer = _make_analyzer()
    result = _rebuild(analyzer, fixture)
    assert result["confidence"] <= 0.5, f"撞顶 case confidence={result['confidence']} 应 ≤ 0.5"
    breakdown = result["confidence_breakdown"]
    assert "top_band_collision" in breakdown["reason"], breakdown
    assert breakdown["saturation_event"]["event"] == "top_band_collision"
    assert result["status"] == "uncertain"
    assert result["type"] is None


def test_case_a_partial_collision_confidence_below_target():
    """1.0/1.0/0.77 撞顶 case:status != certain → confidence < target_confidence(0.8)。"""
    fixture = _load_fixture(CASE_A)
    analyzer = _make_analyzer()
    result = _rebuild(analyzer, fixture)
    if result["status"] != "certain":
        assert result["confidence"] < 0.8
    breakdown = result["confidence_breakdown"]
    # Top-2 撞顶或 Top-3 撞顶其一
    assert "saturation" in breakdown["reason"], breakdown


def test_algorithm_top_field_present():
    """v0.10 result 必须有 algorithm_top.type 和 .score。"""
    fixture = _load_fixture(CASE_A)
    analyzer = _make_analyzer()
    result = _rebuild(analyzer, fixture)
    assert "algorithm_top" in result
    assert result["algorithm_top"]["type"] in {"IEI", "ILI", "ILE", None}
    assert isinstance(result["algorithm_top"]["score"], float)


def test_stability_hint_initialized():
    """_build_result 必须初始化 stability_hint(synthesis 未跑时 consistent=None)。"""
    fixture = _load_fixture(CASE_A)
    analyzer = _make_analyzer()
    result = _rebuild(analyzer, fixture)
    assert "stability_hint" in result
    sh = result["stability_hint"]
    assert sh["algorithm_top"] in {"IEI", "ILI", "ILE", None}
    assert sh["consistent"] is None  # synthesis 未跑
    assert sh["synthesis_verdict"] is None


def test_arbitration_does_not_override_type_when_disagree():
    """v0.10 C3:arbitration disagree → 不覆盖 result.type/candidates。"""
    fixture = _load_fixture(CASE_A)
    analyzer = _make_analyzer()
    result = _rebuild(analyzer, fixture)

    # 手动构造一个 synthesis 与 algorithm Top-1 分歧的情况
    candidates = result["candidates"]
    algo_top = candidates[0]["type"]
    fake_synthesis = {
        "verdict_type": "ESI",  # 不在 top-3
        "coherence_confidence": 0.9,
        "narrative": "fake",
        "main_competitor": "?",
        "why_not_competitor": "fake",
    }
    arbitrated = analyzer._arbitrate(result, candidates, fake_synthesis)

    assert arbitrated["arbitration"]["agrees_with_algorithm"] is False
    assert arbitrated["arbitration"]["suggested_type"] == "ESI"
    # candidates 顺序保持算法层不变
    assert arbitrated["candidates"][0]["type"] == algo_top
    # status 强制 uncertain
    assert arbitrated["status"] == "uncertain"
    # confidence 因为 arbitration disagree 应被强降到 0.4 或更低
    assert arbitrated["confidence"] <= 0.5
    # algorithm_top 字段反映算法 Top-1,不是 verdict
    assert arbitrated["algorithm_top"]["type"] == algo_top


def test_arbitration_agree_keeps_type():
    """C3:synthesis agree with algorithm Top-1 → arbitration agree,不强降 status。"""
    fixture = _load_fixture(CASE_A)
    analyzer = _make_analyzer()
    result = _rebuild(analyzer, fixture)
    candidates = result["candidates"]
    algo_top = candidates[0]["type"]

    fake_synthesis = {
        "verdict_type": algo_top,
        "coherence_confidence": 0.85,
        "narrative": "fake",
        "main_competitor": "?",
        "why_not_competitor": "fake",
    }
    arbitrated = analyzer._arbitrate(result, candidates, fake_synthesis)

    assert arbitrated["arbitration"]["agrees_with_algorithm"] is True
    assert arbitrated["arbitration"]["decision"] == "agree"
    assert arbitrated["stability_hint"]["consistent"] is True


def test_stability_hint_low_coherence_forces_uncertain():
    """C5:coherence < 0.75 → stability_hint.consistent = False → status 强制 uncertain。"""
    fixture = _load_fixture(CASE_A)
    analyzer = _make_analyzer()
    result = _rebuild(analyzer, fixture)
    # 手动把 status 设为 certain 以验证 C5 强制 uncertain
    result["status"] = "certain"
    candidates = result["candidates"]
    algo_top = candidates[0]["type"]

    fake_synthesis = {
        "verdict_type": algo_top,  # 一致但 coherence 低
        "coherence_confidence": 0.4,
    }
    arbitrated = analyzer._arbitrate(result, candidates, fake_synthesis)
    assert arbitrated["stability_hint"]["consistent"] is False
    assert arbitrated["status"] == "uncertain"


def test_enforce_dimension_constraints_demotes_4d():
    """C4:>2 个 4D 元素被截断为 Top-2,其余降为 3D。"""
    analyzer = _make_analyzer()
    decision = {
        "element_dimensions": {
            "Ni": {"dimension": "4D", "vote_4d": 3.0, "rationale": "a"},
            "Te": {"dimension": "4D", "vote_4d": 2.5, "rationale": "b"},
            "Si": {"dimension": "4D", "vote_4d": 1.0, "rationale": "c"},
            "Fi": {"dimension": "4D", "vote_4d": 0.5, "rationale": "d"},
        },
        "synthesis_notes": "test",
    }
    revised, notes = analyzer._enforce_dimension_constraints(decision)
    dims = revised["element_dimensions"]
    assert dims["Ni"]["dimension"] == "4D"
    assert dims["Te"]["dimension"] == "4D"
    assert dims["Si"]["dimension"] == "3D"
    assert dims["Fi"]["dimension"] == "3D"
    assert any("Si" in n for n in notes)
    assert any("Fi" in n for n in notes)


def test_enforce_dimension_constraints_demotes_1d():
    """C4:>1 个 1D 元素时降为 2D。"""
    analyzer = _make_analyzer()
    decision = {
        "element_dimensions": {
            "Se": {"dimension": "1D", "vote_1d": 2.0, "rationale": "a"},
            "Ne": {"dimension": "1D", "vote_1d": 0.5, "rationale": "b"},
        },
        "synthesis_notes": "",
    }
    revised, notes = analyzer._enforce_dimension_constraints(decision)
    dims = revised["element_dimensions"]
    assert dims["Se"]["dimension"] == "1D"  # 最高 vote_1d 保留
    assert dims["Ne"]["dimension"] == "2D"
    assert any("Ne" in n for n in notes)


def test_saturation_does_not_trigger_for_lone_top():
    """单点 1.0 但 Top-2 远低 → 不触发撞顶。"""
    analyzer = _make_analyzer()
    ranked = [
        {"type": "LIE", "score": 1.0},
        {"type": "ILI", "score": 0.6},
        {"type": "LSE", "score": 0.3},
    ]
    assert analyzer._detect_saturation(ranked) is None


def test_saturation_triggers_for_top2_band():
    """1.0/1.0/0.77 → top2_collision。"""
    analyzer = _make_analyzer()
    ranked = [
        {"type": "IEI", "score": 1.0},
        {"type": "ILI", "score": 1.0},
        {"type": "ILE", "score": 0.77},
    ]
    ev = analyzer._detect_saturation(ranked)
    assert ev is not None
    assert ev["event"] == "top2_collision"


def test_calibrate_confidence_status_uncertain_caps():
    """status != certain → confidence ≤ uncertain_confidence_cap(0.5)。"""
    analyzer = _make_analyzer()
    top = {"type": "LIE", "score": 0.9}
    conf, breakdown = analyzer._calibrate_confidence(
        top=top,
        status="uncertain",
        saturation_event=None,
        partial_recovered=False,
        arbitration_decision=None,
    )
    assert conf <= 0.5
    assert "status_uncertain" in breakdown["reason"]


def test_calibrate_confidence_certain_no_saturation_passthrough():
    """status=certain + 无撞顶 + 无 arbitration → confidence = raw_score。"""
    analyzer = _make_analyzer()
    top = {"type": "LIE", "score": 0.85}
    conf, breakdown = analyzer._calibrate_confidence(
        top=top,
        status="certain",
        saturation_event=None,
        partial_recovered=False,
        arbitration_decision=None,
    )
    assert conf == 0.85
    assert breakdown["reason"] == "raw"
