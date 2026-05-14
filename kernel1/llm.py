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
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            recovered = self._recover_partial_quotes(text)
            if recovered:
                self.last_error = "Recovered partial JSON from truncated LLM response"
                return recovered
            raise

    def _recover_partial_quotes(self, text: str) -> dict[str, Any] | None:
        start = text.find('"quotes"')
        if start < 0:
            return None
        array_start = text.find("[", start)
        if array_start < 0:
            return None

        objects: list[dict[str, Any]] = []
        depth = 0
        obj_start: int | None = None
        in_string = False
        escape = False
        for index, char in enumerate(text[array_start + 1 :], start=array_start + 1):
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                if depth == 0:
                    obj_start = index
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and obj_start is not None:
                    chunk = text[obj_start : index + 1]
                    try:
                        objects.append(json.loads(chunk))
                    except json.JSONDecodeError:
                        pass
                    obj_start = None
                    if len(objects) >= 8:
                        break
        if not objects:
            return None
        return {
            "quotes": objects,
            "dichotomy_signals": {},
            "conflicts": [{"topic": "LLM输出截断", "evidence": [], "reason": "仅恢复已闭合的证据项"}],
            "insufficiency": ["LLM JSON 输出被截断，已使用部分恢复结果。"],
        }
