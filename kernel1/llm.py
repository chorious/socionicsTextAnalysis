from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


LOG_DIR = Path(__file__).resolve().parent / "logs"


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = os.getenv("KERNEL1_LLM_BASE_URL", "http://127.0.0.1:8000/v1/chat/completions")
    model: str = os.getenv("KERNEL1_LLM_MODEL", "qwen3.6-27b")
    api_key: str = os.getenv("KERNEL1_LLM_API_KEY", "EMPTY")
    timeout: int = int(os.getenv("KERNEL1_LLM_TIMEOUT", "90"))
    max_tokens: int = int(os.getenv("KERNEL1_LLM_MAX_TOKENS", "4096"))
    enabled: bool = os.getenv("KERNEL1_LLM_ENABLED", "0") == "1"


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()
        self.last_error: str | None = None
        self.last_raw_path: str | None = None
        self.last_request_meta: dict[str, Any] | None = None

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        self.last_error = None
        self.last_raw_path = None
        self.last_request_meta = None
        if not self.config.enabled:
            self.last_error = "LLM disabled"
            return None

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        self.last_request_meta = {
            "base_url": self.config.base_url,
            "model": self.config.model,
            "timeout": self.config.timeout,
            "max_tokens": self.config.max_tokens,
        }

        try:
            response = requests.post(
                self.config.base_url,
                headers=headers,
                json=payload,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            self._write_raw(content)
            return self._parse_json_content(content)
        except Exception as exc:
            self.last_error = str(exc)
            return None

    def _write_raw(self, content: str) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"llm_raw_{int(time.time() * 1000)}.txt"
        path.write_text(content, encoding="utf-8")
        self.last_raw_path = str(path)

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        elif not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        return json.loads(text)
