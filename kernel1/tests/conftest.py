"""Pytest fixtures for kernel1 unit tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kernel1.core import BASE_DIR, Kernel1Analyzer
from kernel1.llm import LLMClient, LLMConfig


SAMPLE_TEXT_PATH = BASE_DIR / "samples" / "sample_input.txt"
QA_SMOKE_OUTPUT_PATH = BASE_DIR / "outputs" / "edited-qa-smoke-001.json"


@pytest.fixture
def analyzer_heuristic() -> Kernel1Analyzer:
    """Analyzer with LLM disabled — falls back to heuristic extraction."""
    return Kernel1Analyzer(llm=LLMClient(LLMConfig(enabled=False)))


@pytest.fixture
def sample_text() -> str:
    return SAMPLE_TEXT_PATH.read_text(encoding="utf-8")


@pytest.fixture
def stub_llm(monkeypatch):
    """Helper to monkeypatch LLMClient.chat_json with a pre-recorded response."""

    def _install(response):
        def fake_chat_json(self, system_prompt, user_prompt):  # noqa: ARG001
            return response

        monkeypatch.setattr(LLMClient, "chat_json", fake_chat_json)

    return _install


@pytest.fixture
def qa_smoke_extraction() -> list[dict]:
    """Load the evidence_chain from the canonical QA smoke output for replay tests."""
    data = json.loads(QA_SMOKE_OUTPUT_PATH.read_text(encoding="utf-8"))
    return data.get("evidence_chain", [])
