"""Tests for the ref_cards selection feature."""
from __future__ import annotations

from kernel1.core import AnalyzeOptions, Kernel1Analyzer
from kernel1.llm import LLMClient, LLMConfig


def _make_analyzer(filename: str | None = None) -> Kernel1Analyzer:
    return Kernel1Analyzer(
        llm=LLMClient(LLMConfig(enabled=False)),
        options=AnalyzeOptions(ref_cards_filename=filename),
    )


def test_list_ref_cards_returns_at_least_default():
    files = Kernel1Analyzer.list_ref_cards()
    assert "reference_cards.md" in files
    # Sorted lexicographically
    assert files == sorted(files)


def test_default_ref_cards_used_when_none_specified():
    a = _make_analyzer(None)
    prompt = a.extraction_prompt
    # Default now prefers the docx-sourced Socionics variant (with 32 cards)
    # and falls back to the compact reference_cards.md only when it is missing.
    assert "IND TM-A" in prompt
    assert a._active_ref_cards_name() == "reference_cards_socionics.md"


def test_compact_ref_cards_can_still_be_loaded_explicitly():
    a = _make_analyzer("reference_cards.md")
    prompt = a.extraction_prompt
    assert "IND TM-A" in prompt
    assert "字典卡片" in prompt
    assert a._active_ref_cards_name() == "reference_cards.md"


def test_socionics_ref_cards_loaded_when_specified():
    a = _make_analyzer("reference_cards_socionics.md")
    prompt = a.extraction_prompt
    # Socionics-rich file has 32 Function-Position cards
    assert "### Te 1号" in prompt
    assert "### Ni 4号" in prompt
    # Both files still keep the 19-code legend
    assert "IND TM-A" in prompt
    assert a._active_ref_cards_name() == "reference_cards_socionics.md"


def test_invalid_filename_silently_falls_back_to_default():
    a = _make_analyzer("evil/../../etc/passwd")
    assert a._active_ref_cards_name() == "reference_cards_socionics.md"


def test_nonexistent_filename_falls_back_to_default():
    a = _make_analyzer("reference_cards_doesnotexist.md")
    assert a._active_ref_cards_name() == "reference_cards_socionics.md"


def test_filename_outside_pattern_falls_back():
    a = _make_analyzer("malicious.md")
    assert a._active_ref_cards_name() == "reference_cards_socionics.md"


def test_result_carries_active_ref_cards(sample_text):
    a = _make_analyzer("reference_cards_socionics.md")
    result = a.analyze(sample_text, case_id="ref-cards-smoke")
    assert result["preprocess"]["ref_cards"] == "reference_cards_socionics.md"


def test_list_endpoint_via_test_client():
    """End-to-end: /kernel1/list-refcards returns both files."""
    from fastapi.testclient import TestClient
    from kernel1.app import app

    client = TestClient(app)
    r = client.get("/kernel1/list-refcards")
    assert r.status_code == 200
    data = r.json()
    assert "files" in data
    assert "reference_cards.md" in data["files"]
    assert "reference_cards_socionics.md" in data["files"]
    assert data["default"] == "reference_cards_socionics.md"


def test_analyze_endpoint_accepts_ref_cards_param():
    """End-to-end: /kernel1/analyze with ref_cards uses the selected file."""
    from fastapi.testclient import TestClient
    from kernel1.app import app

    client = TestClient(app)
    sample = (
        "我经常会先观察一个事情未来可能怎么变化,而不是马上下结论。"
        "比起把当下的细节都处理好,我更在意这个方向后面会不会走歪。\n\n"
        "跟人合作时,我会主动拆流程、看效率和投入产出。"
    )
    r = client.post("/kernel1/analyze", json={
        "text": sample,
        "case_id": "ref-cards-api",
        "ref_cards": "reference_cards_socionics.md",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["preprocess"]["ref_cards"] == "reference_cards_socionics.md"
