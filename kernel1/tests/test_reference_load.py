"""Verify extraction_prompt loads reference_cards.md and error examples."""
from __future__ import annotations


IND_CODES = [
    "IND TM-A", "IND F1-A", "IND MN-A", "IND MN-C", "IND VT-A",
    "IND VT-B", "IND VT-F", "IND NR-D", "IND NR-A", "IND 1D-A",
    "IND LD-A", "IND LD-E", "IND 1D-L", "IND ST-A", "IND HD-B",
    "IND HD-F", "IND VR-A", "IND NV-A", "IND NV-D",
]


def test_extraction_prompt_includes_reference(analyzer_heuristic):
    prompt = analyzer_heuristic.extraction_prompt
    for ind in IND_CODES:
        assert ind in prompt, f"missing {ind} in prompt"
    assert "错误示例" in prompt
    assert "显性/感觉" in prompt


def test_extraction_prompt_includes_dictionary_examples(analyzer_heuristic):
    """Default ref cards (Socionics variant) carries Function×Position examples."""
    prompt = analyzer_heuristic.extraction_prompt
    assert "我一直能提前看到事情的走向" in prompt
    # docx-sourced variant uses Function×Position card headings
    assert "### Te 1号" in prompt
