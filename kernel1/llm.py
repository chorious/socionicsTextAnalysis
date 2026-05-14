from __future__ import annotations

import concurrent.futures
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
        """同步单调用，更新共享状态（last_error/last_raw_path/last_request_meta）。"""
        self.last_error = None
        self.last_raw_path = None
        self.last_request_meta = None
        result, error, raw_path, meta = self._chat_json_single(system_prompt, user_prompt)
        self.last_error = error
        self.last_raw_path = raw_path
        self.last_request_meta = meta
        return result

    def chat_json_parallel(
        self, requests: list[tuple[str, str]]
    ) -> list[dict[str, Any] | None]:
        """
        并发执行多个 chat_json 调用。
        requests: [(system_prompt, user_prompt), ...]
        返回 result 列表，顺序对应；失败的位置返回 None。
        并发时不共享 last_error/last_raw_path，错误信息内嵌到 result 的 _llm_error/_llm_raw_path 字段。
        """
        if not self.config.enabled:
            return [None] * len(requests)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(requests)) as executor:
            futures = [
                executor.submit(self._chat_json_single, sys, usr)
                for sys, usr in requests
            ]
            results: list[dict[str, Any] | None] = []
            for f in futures:
                result, error, raw_path, _meta = f.result()
                if result is not None and (error or raw_path):
                    result = dict(result)
                    if error:
                        result["_llm_error"] = error
                    if raw_path:
                        result["_llm_raw_path"] = raw_path
                results.append(result)
            return results

    def _chat_json_single(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[dict[str, Any] | None, str | None, str | None, dict[str, Any] | None]:
        """内部单调用，不修改共享状态，返回 (result, error, raw_path, meta)。"""
        if not self.config.enabled:
            return None, "LLM disabled", None, None

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
        meta = {
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
            raw_path = self._write_raw(content)
            parsed = self._parse_json_content(content)
            return parsed, None, raw_path, meta
        except Exception as exc:
            return None, str(exc), None, meta

    def _write_raw(self, content: str) -> str:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"llm_raw_{int(time.time() * 1000)}.txt"
        path.write_text(content, encoding="utf-8")
        return str(path)

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
                recovered["_llm_error"] = "Recovered partial JSON from truncated LLM response"
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
