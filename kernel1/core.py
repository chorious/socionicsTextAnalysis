from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .llm import LLMClient


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
MODEL_A_PATH = BASE_DIR / "model_a.json"
EXTRACTION_PROMPT_PATH = BASE_DIR / "prompts" / "evidence_extraction.md"
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "outputs"

DIMENSION_POSITIONS = {
    "1D": {4, 5},
    "2D": {3, 6},
    "3D": {2, 7},
    "4D": {1, 8},
}
VALUED_POSITIONS = {1, 2, 5, 6}
MENTAL_POSITIONS = {1, 2, 3, 4}
STRONG_POSITIONS = {1, 2, 7, 8}
ACCEPTING_POSITIONS = {1, 3, 5, 7}
PRODUCING_POSITIONS = {2, 4, 6, 8}
INERT_POSITIONS = {1, 4, 6, 7}
CONTACT_POSITIONS = {2, 3, 5, 8}
GUIDE_POSITIONS = {1, 4, 5, 8}
SEPARATE_POSITIONS = {2, 3, 6, 7}
RATIONAL_ELEMENTS = {"Te", "Ti", "Fe", "Fi"}
IRRATIONAL_ELEMENTS = {"Ne", "Ni", "Se", "Si"}
STATIC_ELEMENTS = {"Ne", "Ti", "Fi", "Se"}
DYNAMIC_ELEMENTS = {"Ni", "Si", "Fe", "Te"}
STATIC_TYPES = {"ILE", "LII", "ESI", "SEE", "EII", "IEE", "LSI", "SLE"}
DYNAMIC_TYPES = {"SEI", "ESE", "EIE", "IEI", "LIE", "ILI", "LSE", "SLI"}

ELEMENT_GROUPS = {
    "N": {"Ne", "Ni"},
    "S": {"Se", "Si"},
    "T": {"Te", "Ti"},
    "F": {"Fe", "Fi"},
    "E": {"Ne", "Se", "Te", "Fe"},
    "I": {"Ni", "Si", "Ti", "Fi"},
    "R": {"Te", "Ti", "Fe", "Fi"},
    "Ir": {"Ne", "Ni", "Se", "Si"},
}

# 赖宁四象限二分法：quadra 集合
LANING_QUADRA: dict[str, frozenset[str]] = {
    "democratic":  frozenset({"ILE", "LII", "ESE", "SEI", "SEE", "ESI", "LIE", "ILI"}),  # Alpha + Gamma
    "aristocratic": frozenset({"SLE", "LSI", "EIE", "IEI", "IEE", "EII", "LSE", "SLI"}),  # Beta + Delta
    "merry":       frozenset({"ILE", "LII", "ESE", "SEI", "SLE", "LSI", "EIE", "IEI"}),  # Alpha + Beta
    "serious":     frozenset({"SEE", "ESI", "LIE", "ILI", "IEE", "EII", "LSE", "SLI"}),  # Gamma + Delta
    "judicious":   frozenset({"ILE", "LII", "ESE", "SEI", "IEE", "EII", "LSE", "SLI"}),  # Alpha + Delta
    "decisive":    frozenset({"SLE", "LSI", "EIE", "IEI", "SEE", "ESI", "LIE", "ILI"}),  # Beta + Gamma
}

# IND 行为指标 → 位置特征 profile
# 每个指标映射到它最强指向的维度/强弱/重视/环路字段，用于给 extraction.quotes 里的 indicator 字段加分
IND_PROFILES: dict[str, dict[str, Any]] = {
    # 4D 全局性——主导/演示（位置1/8）
    "IND TM-A": {"dimension_hint": "4D", "strength_signal": "strong", "mental_signal": "mental"},
    "IND F1-A": {"dimension_hint": "4D", "strength_signal": "strong", "valued_signal": "valued"},
    # 意识环——位置1-4
    "IND MN-A": {"mental_signal": "mental"},
    "IND MN-C": {"mental_signal": "mental", "accepting_signal": "producing"},
    # 生机环——位置5-8
    "IND VT-A": {"mental_signal": "vital"},
    "IND VT-B": {"mental_signal": "vital", "contact_signal": "inert"},
    "IND VT-F": {"mental_signal": "vital", "valued_signal": "unvalued"},
    # 2D 规范——角色/激活（位置3/6）
    "IND NR-D": {"dimension_hint": "2D"},
    "IND NR-A": {"dimension_hint": "2D", "strength_signal": "weak"},
    # 1D 极弱——薄弱/暗示（位置4/5）
    "IND 1D-A": {"dimension_hint": "1D", "strength_signal": "weak"},
    "IND LD-A": {"dimension_hint": "1D", "strength_signal": "weak"},
    "IND LD-E": {"dimension_hint": "1D", "strength_signal": "weak", "valued_signal": "unvalued"},
    "IND 1D-L": {"dimension_hint": "1D", "strength_signal": "weak", "valued_signal": "unvalued"},
    # 3D 情境——创造/忽略（位置2/7）
    "IND ST-A": {"dimension_hint": "3D", "strength_signal": "strong"},
    "IND HD-B": {"dimension_hint": "3D"},
    "IND HD-F": {"dimension_hint": "3D", "valued_signal": "unvalued"},
    # 重视/非重视
    "IND VR-A": {"valued_signal": "valued"},
    "IND NV-A": {"valued_signal": "unvalued", "strength_signal": "weak"},
    "IND NV-D": {"valued_signal": "unvalued"},
}

# L1 阻塞轴描述：轴 key → 人类可读描述 + 需要寻找的证据方向
AXIS_DESCRIPTIONS: dict[str, str] = {
    "Ni_vs_Si": "区分 Ni（时间趋势/预感）与 Si（感官记忆/体感舒适）——找文本里关于时间感、未来走向、过去经验、身体舒适度的描述",
    "Ne_vs_Se": "区分 Ne（外部可能性）与 Se（外部力量/现实掌控）——找关于发散可能性、介入改变现实、边界与力量的描述",
    "Te_vs_Ti": "区分 Te（外部效率/结果）与 Ti（内部结构/框架）——找关于操作步骤、数据结果、逻辑自洽、框架完整性的描述",
    "Fe_vs_Fi": "区分 Fe（外部情绪氛围）与 Fi（内部价值关系）——找关于带动气氛、关系质量、立场对错、道德距离的描述",
    "Ni_vs_Ne": "区分 Ni（内倾直觉/时间流向）与 Ne（外倾直觉/可能性）——找关于是追踪单一趋势还是发散多种可能性的描述",
    "Si_vs_Se": "区分 Si（内倾感觉/体感记忆）与 Se（外倾感觉/空间力量）——找关于是关注内在舒适还是外部掌控的描述",
    "Te_vs_Fe": "区分 Te（逻辑效率导向）与 Fe（情感氛围导向）——找关于用逻辑还是情感驱动决策的描述",
    "Ti_vs_Fi": "区分 Ti（内部逻辑框架）与 Fi（内部道德价值）——找关于是追求一致性逻辑还是追求价值立场的描述",
    "2nd_vs_7th": "区分 2nd 创造（主动、重视、意识环）与 7th 忽略（强但非重视、生机环）——找该功能是主动谈起还是被动应付、厌倦",
}

# 元素对 → 轴 key 的归一化映射（用于 _identify_blocking_axis）
ELEMENT_PAIR_TO_AXIS: dict[frozenset, str] = {
    frozenset({"Ni", "Si"}): "Ni_vs_Si",
    frozenset({"Ne", "Se"}): "Ne_vs_Se",
    frozenset({"Te", "Ti"}): "Te_vs_Ti",
    frozenset({"Fe", "Fi"}): "Fe_vs_Fi",
    frozenset({"Ni", "Ne"}): "Ni_vs_Ne",
    frozenset({"Si", "Se"}): "Si_vs_Se",
    frozenset({"Te", "Fe"}): "Te_vs_Fe",
    frozenset({"Ti", "Fi"}): "Ti_vs_Fi",
}


@dataclass(frozen=True)
class AnalyzeOptions:
    min_chars: int = 80
    max_chars: int = 12000
    top_threshold: float = 0.65
    margin_threshold: float = 0.12
    min_evidence: int = 3


class Kernel1Analyzer:
    def __init__(self, llm: LLMClient | None = None, options: AnalyzeOptions | None = None) -> None:
        self.llm = llm or LLMClient()
        self.options = options or AnalyzeOptions()
        self.model_a = self._load_model_a()
        self.extraction_prompt = EXTRACTION_PROMPT_PATH.read_text(encoding="utf-8")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def analyze(self, text: str, case_id: str | None = None) -> dict[str, Any]:
        case_id = case_id or f"case-{int(time.time())}"
        cleaned = self._normalize_text(text)
        rejected = self._validate_input(case_id, cleaned)
        if rejected:
            self._write_artifacts(case_id, rejected)
            return rejected

        prepared = self._prepare_analysis_input(cleaned)
        extraction = self._extract_evidence(prepared["analysis_text"], prepared)
        candidates = self._score_candidates(extraction)
        result = self._build_result(case_id, candidates, extraction, prepared)
        result = self._refine(result, extraction, candidates, prepared, case_id)
        if not result.get("report"):
            result["report"] = self._render_report(result)
        self._write_artifacts(case_id, result)
        return result

    def analyze_qa(self, qa_items: list[dict[str, str]], case_id: str | None = None) -> dict[str, Any]:
        case_id = case_id or f"case-{int(time.time())}"
        prepared = self.prepare_qa_items(qa_items)
        rejected = self._validate_input(case_id, prepared["analysis_text"])
        if rejected:
            self._write_artifacts(case_id, rejected)
            return rejected

        extraction = self._extract_evidence(prepared["analysis_text"], prepared)
        candidates = self._score_candidates(extraction)
        result = self._build_result(case_id, candidates, extraction, prepared)
        result = self._refine(result, extraction, candidates, prepared, case_id)
        if not result.get("report"):
            result["report"] = self._render_report(result)
        self._write_artifacts(case_id, result)
        return result

    def parse_qa(self, text: str) -> dict[str, Any]:
        cleaned = self._normalize_text(text)
        qa_items = self._split_qa(cleaned)
        return {
            "mode": "qa_answers_only" if qa_items else "plain_text",
            "qa_count": len(qa_items),
            "qa_items": qa_items,
            "original_length": len(cleaned),
            "analysis_length": sum(len(item.get("answer", "")) for item in qa_items) if qa_items else len(cleaned),
        }

    def _load_model_a(self) -> dict[str, Any]:
        return json.loads(MODEL_A_PATH.read_text(encoding="utf-8"))

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\n{3,}", "\n\n", text.strip())

    def _validate_input(self, case_id: str, text: str) -> dict[str, Any] | None:
        if self._looks_mojibake(text):
            return {
                "case_id": case_id,
                "status": "rejected",
                "type": None,
                "alias": None,
                "quadra": None,
                "confidence": 0.0,
                "candidates": [],
                "model_a": [],
                "evidence_chain": [],
                "input_encoding": "utf-8",
                "extraction_source": "rejected",
                "llm_error": None,
                "conflicts": [],
                "insufficiency": ["输入文本疑似编码错误或乱码，请用 UTF-8/正常中文重新粘贴。"],
                "report": "判型状态：拒绝分析。输入文本疑似乱码，请重新复制正常中文文本。",
            }
        if len(text) < self.options.min_chars:
            return {
                "case_id": case_id,
                "status": "rejected",
                "type": None,
                "alias": None,
                "quadra": None,
                "confidence": 0.0,
                "candidates": [],
                "model_a": [],
                "evidence_chain": [],
                "input_encoding": "utf-8",
                "conflicts": [],
                "insufficiency": ["输入文本过短，无法进行稳定判型。"],
                "report": "判型状态：拒绝分析。输入文本过短，建议提供至少一段完整自述。",
            }
        if len(text) > self.options.max_chars:
            return {
                "case_id": case_id,
                "status": "rejected",
                "type": None,
                "alias": None,
                "quadra": None,
                "confidence": 0.0,
                "candidates": [],
                "model_a": [],
                "evidence_chain": [],
                "input_encoding": "utf-8",
                "conflicts": [],
                "insufficiency": [f"输入文本超过 {self.options.max_chars} 字，请先压缩或分段。"],
                "report": f"判型状态：拒绝分析。输入文本超过 {self.options.max_chars} 字。",
            }
        return None

    def _looks_mojibake(self, text: str) -> bool:
        if not text:
            return False
        markers = ("譏", "諤", "蜊", "荳", "蝙", "縲", "螳", "逧", "豕", "窶", "莨", "隸")
        marker_count = sum(text.count(marker) for marker in markers)
        replacement_count = text.count("�")
        ratio = (marker_count + replacement_count) / max(len(text), 1)
        return marker_count >= 8 and ratio > 0.01

    def _prepare_analysis_input(self, text: str) -> dict[str, Any]:
        qa_items = self._split_qa(text)
        if qa_items:
            return self.prepare_qa_items(qa_items, original_length=len(text))
        else:
            analysis_text = text
            mode = "plain_text"

        return {
            "mode": mode,
            "qa_count": len(qa_items),
            "qa_items": qa_items[:30],
            "analysis_text": analysis_text,
            "original_length": len(text),
            "analysis_length": len(analysis_text),
        }

    def prepare_qa_items(
        self, qa_items: list[dict[str, str]], original_length: int | None = None
    ) -> dict[str, Any]:
        normalized_items = []
        for item in qa_items:
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            if answer:
                normalized_items.append({"question": question, "answer": answer})

        answer_text = "\n\n".join(
            f"回答{i + 1}: {item['answer']}" for i, item in enumerate(normalized_items)
        )
        return {
            "mode": "qa_answers_only",
            "qa_count": len(normalized_items),
            "qa_items": normalized_items[:30],
            "analysis_text": answer_text,
            "original_length": original_length if original_length is not None else len(answer_text),
            "analysis_length": len(answer_text),
            "source": "edited_qa_json",
        }

    def _split_qa(self, text: str) -> list[dict[str, str]]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        items: list[dict[str, str]] = []
        current_question: str | None = None
        current_answer: list[str] = []

        for line in lines:
            if self._looks_like_question(line):
                if current_question and current_answer:
                    items.append({"question": current_question, "answer": "\n".join(current_answer).strip()})
                current_question = line
                current_answer = []
            elif current_question:
                current_answer.append(line)

        if current_question and current_answer:
            items.append({"question": current_question, "answer": "\n".join(current_answer).strip()})

        total_answer_chars = sum(len(item["answer"]) for item in items)
        return items if len(items) >= 2 and total_answer_chars >= self.options.min_chars else []

    def _looks_like_question(self, line: str) -> bool:
        compact = line.strip()
        if len(compact) > 90:
            return False
        numbered = re.match(r"^\s*\d+[\.．、)]\s*", compact) is not None
        question_word = any(word in compact for word in ("如何", "怎么", "什么", "是否", "能否", "觉得", "为什么"))
        punctuation = compact.endswith(("?", "？", "吗"))
        return punctuation or (numbered and question_word)

    def _extract_evidence(self, text: str, prepared: dict[str, Any]) -> dict[str, Any]:
        if prepared["mode"] == "qa_answers_only":
            user_prompt = (
                "请根据以下问卷回答提取 Socionics 判型证据。只分析回答，不要把题目本身当成证据。只输出 JSON。\n\n"
                f"问卷回答：\n{text}"
            )
        else:
            user_prompt = (
                "请根据以下用户文本提取 Socionics 判型证据。只输出 JSON。\n\n"
                f"用户文本：\n{text}"
            )
        llm_result = self.llm.chat_json(self.extraction_prompt, user_prompt)
        if not self._is_valid_extraction(llm_result):
            repaired = self._repair_extraction_schema(llm_result, prepared)
            if self._is_valid_extraction(repaired):
                llm_result = repaired
        if self._is_valid_extraction(llm_result):
            raw_normalized = self._normalize_extraction(llm_result)
            if isinstance(llm_result, dict) and llm_result.get("_llm_error"):
                raw_normalized["_llm_error"] = llm_result.get("_llm_error")
            if isinstance(llm_result, dict) and llm_result.get("_llm_raw_path"):
                raw_normalized["_llm_raw_path"] = llm_result.get("_llm_raw_path")
            # 阶段 2：超过 8 条时调用整合精炼
            if len(raw_normalized.get("quotes", [])) > 8:
                synthesized = self._synthesize_evidence(raw_normalized, prepared)
                if synthesized:
                    return self._ensure_qa_evidence_coverage(synthesized, prepared)
            raw_normalized["_source"] = "llm"
            return self._ensure_qa_evidence_coverage(raw_normalized, prepared)
        fallback = self._heuristic_extract(text)
        fallback["_source"] = "heuristic"
        fallback["_llm_error"] = self.llm.last_error
        fallback["_llm_raw_path"] = getattr(self.llm, "last_raw_path", None)
        fallback["_llm_request"] = getattr(self.llm, "last_request_meta", None)
        if isinstance(llm_result, dict) and isinstance(llm_result.get("quotes"), list):
            fallback["_schema_invalid"] = True
            fallback["_llm_error"] = "LLM returned invalid extraction schema"
        return self._ensure_qa_evidence_coverage(fallback, prepared)

    def _is_valid_extraction(self, data: Any) -> bool:
        return (
            isinstance(data, dict)
            and isinstance(data.get("quotes"), list)
            and any(isinstance(item, dict) for item in data.get("quotes", []))
        )

    def _repair_extraction_schema(
        self, data: Any, prepared: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not self.llm.config.enabled:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("quotes"), list):
            return None
        if any(isinstance(item, dict) for item in data.get("quotes", [])):
            return None

        raw_quotes = [str(item)[:180] for item in data.get("quotes", [])[:30] if str(item).strip()]
        if not raw_quotes:
            return None

        system_prompt = (
            "你是 Socionics Kernel1 的 JSON schema 修复器。"
            "输入的 quotes 是字符串数组，必须改写为标准 quote 对象数组。"
            "只输出合法 JSON，不要 Markdown。"
        )
        qa_hint = ""
        if prepared.get("mode") == "qa_answers_only":
            qa_hint = "\n问答索引可从原文的“回答N:”推断；无法确定则不要填写 qa_index。"
        user_prompt = (
            "请把这些原始 quote 字符串转换成结构化 Socionics evidence quotes。"
            "每条必须包含 quote/indicator/element_hint/dimension_hint/position_hint/confidence/"
            "strength_signal/valued_signal/mental_signal/accepting_signal/contact_signal/"
            "guide_signal/evidence_type/reason。"
            "element_hint 只能是 Ne/Ni/Se/Si/Te/Ti/Fe/Fi/unknown；"
            "dimension_hint 只能是 1D/2D/3D/4D/unknown。"
            "如果无法可靠判断元素或维度，宁可少输出，不要输出 unknown 占位。"
            f"{qa_hint}\n\n原始 quotes:\n{json.dumps(raw_quotes, ensure_ascii=False)}\n\n"
            f"上下文节选:\n{prepared.get('analysis_text', '')[:3000]}"
        )
        repaired = self.llm.chat_json(system_prompt, user_prompt)
        if isinstance(repaired, dict):
            repaired["_source"] = "llm_schema_repaired"
        return repaired

    def _normalize_extraction(self, data: dict[str, Any]) -> dict[str, Any]:
        allowed_elements = {"Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi", "unknown"}
        allowed_dimensions = {"1D", "2D", "3D", "4D", "unknown"}
        cleaned_quotes = []
        for item in data.get("quotes", [])[:30]:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote", "")).strip()[:90]
            if not quote:
                continue
            element = item.get("element_hint") if item.get("element_hint") in allowed_elements else "unknown"
            dimension = item.get("dimension_hint") if item.get("dimension_hint") in allowed_dimensions else "unknown"
            cleaned_quotes.append(
                {
                    "quote": quote,
                    "indicator": str(item.get("indicator", "unknown"))[:40],
                    "element_hint": element,
                    "dimension_hint": dimension,
                    "position_hint": item.get("position_hint") if isinstance(item.get("position_hint"), int) else None,
                    "confidence": self._bounded_float(item.get("confidence"), 0.5),
                    "strength_signal": self._allowed_value(item.get("strength_signal"), {"strong", "weak", "unknown"}),
                    "valued_signal": self._allowed_value(item.get("valued_signal"), {"valued", "unvalued", "unknown"}),
                    "mental_signal": self._allowed_value(item.get("mental_signal"), {"mental", "vital", "unknown"}),
                    "accepting_signal": self._allowed_value(item.get("accepting_signal"), {"accepting", "producing", "unknown"}),
                    "contact_signal": self._allowed_value(item.get("contact_signal"), {"contact", "inert", "unknown"}),
                    "guide_signal": self._allowed_value(item.get("guide_signal"), {"guide", "separate", "unknown"}),
                    "evidence_type": self._allowed_value(
                        item.get("evidence_type"),
                        {"identity", "comfort", "stress", "tool", "avoidance", "flexibility", "uncertainty", "keyword"},
                    ),
                    "reason": str(item.get("reason", ""))[:50],
                }
            )

        # 按 (quote前30字, element, dimension) 强去重；同 (element, dimension) 组合最多 3 条
        deduped: list[dict[str, Any]] = []
        seen_quote_keys: set[tuple] = set()
        dim_element_count: dict[tuple, int] = {}
        for q in cleaned_quotes:
            key = (q.get("quote", "")[:30], q.get("element_hint", ""), q.get("dimension_hint", ""))
            if key in seen_quote_keys:
                continue
            dim_key = (q.get("element_hint", ""), q.get("dimension_hint", ""))
            if dim_element_count.get(dim_key, 0) >= 3:
                continue
            seen_quote_keys.add(key)
            dim_element_count[dim_key] = dim_element_count.get(dim_key, 0) + 1
            deduped.append(q)
        data["quotes"] = deduped
        # 规范化 conflicts，新增 conflict_kind 字段
        raw_conflicts = data.get("conflicts", []) if isinstance(data.get("conflicts"), list) else []
        cleaned_conflicts = []
        for c in raw_conflicts[:5]:
            if not isinstance(c, dict):
                continue
            kind = c.get("conflict_kind", "dimension")
            if kind not in {"dimension", "signal"}:
                kind = "dimension"
            cleaned_conflicts.append({
                "topic": str(c.get("topic", ""))[:60],
                "evidence": [str(e)[:60] for e in c.get("evidence", [])[:2]] if isinstance(c.get("evidence"), list) else [],
                "reason": str(c.get("reason", ""))[:80],
                "conflict_kind": kind,
            })
        data["conflicts"] = cleaned_conflicts
        data["insufficiency"] = (
            [str(item)[:80] for item in data.get("insufficiency", [])[:5]]
            if isinstance(data.get("insufficiency"), list)
            else []
        )
        if not isinstance(data.get("dichotomy_signals"), dict):
            data["dichotomy_signals"] = {}

        # 规范化 laning_signals
        allowed_laning_keys = {"democratic", "aristocratic", "merry", "serious", "judicious", "decisive"}
        raw_laning = data.get("laning_signals", {})
        cleaned_laning: dict[str, Any] = {}
        if isinstance(raw_laning, dict):
            for key, sig in raw_laning.items():
                if not isinstance(sig, dict):
                    continue
                lean_val = sig.get("lean", "unknown")
                if lean_val not in allowed_laning_keys and lean_val != "unknown":
                    lean_val = "unknown"
                conf = self._bounded_float(sig.get("confidence"), 0.0)
                evidence = [str(e)[:60] for e in sig.get("evidence", [])[:2]] if isinstance(sig.get("evidence"), list) else []
                if lean_val != "unknown" and conf > 0:
                    cleaned_laning[key] = {"lean": lean_val, "confidence": conf, "evidence": evidence}
        data["laning_signals"] = cleaned_laning
        return data

    def _ensure_qa_evidence_coverage(
        self, extraction: dict[str, Any], prepared: dict[str, Any]
    ) -> dict[str, Any]:
        if prepared.get("mode") != "qa_answers_only":
            return extraction

        qa_items = prepared.get("qa_items", [])
        if not qa_items:
            return extraction

        covered_extraction = dict(extraction)
        quotes = self._attach_qa_context_to_quotes(covered_extraction.get("quotes", []), prepared)
        covered_indexes = {q.get("qa_index") for q in quotes if isinstance(q.get("qa_index"), int)}
        missing_indexes: list[int] = []
        for index, item in enumerate(qa_items, start=1):
            if index in covered_indexes:
                continue
            answer = str(item.get("answer", "")).strip()
            if not answer:
                continue
            missing_indexes.append(index)

        target_count = self._evidence_target_count(prepared)
        covered_extraction["quotes"] = self._select_final_quotes(quotes, target_count=target_count, prepared=prepared)
        covered_extraction["_qa_coverage"] = {
            "covered": len({q.get("qa_index") for q in covered_extraction["quotes"] if isinstance(q.get("qa_index"), int)}),
            "total": len(qa_items),
            "missing_indexes": missing_indexes,
        }
        if missing_indexes:
            insufficiency = list(covered_extraction.get("insufficiency", []))
            insufficiency.append(f"问答覆盖不足：缺少 Q{', Q'.join(str(i) for i in missing_indexes[:12])} 的结构化证据")
            covered_extraction["insufficiency"] = insufficiency[:6]
        return covered_extraction

    def _attach_qa_context_to_quotes(
        self, quotes: list[dict[str, Any]], prepared: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if prepared.get("mode") != "qa_answers_only":
            return [dict(q) for q in quotes]

        qa_items = prepared.get("qa_items", [])
        annotated: list[dict[str, Any]] = []
        for q in quotes:
            new_q = dict(q)
            qa_index = new_q.get("qa_index")
            if not isinstance(qa_index, int):
                qa_index = self._match_quote_to_qa_index(str(new_q.get("quote", "")), qa_items)
            if isinstance(qa_index, int) and 1 <= qa_index <= len(qa_items):
                new_q["qa_index"] = qa_index
                new_q.setdefault("qa_question", str(qa_items[qa_index - 1].get("question", ""))[:90])
            annotated.append(new_q)
        return annotated

    def _match_quote_to_qa_index(self, quote: str, qa_items: list[dict[str, str]]) -> int | None:
        quote_key = self._match_key(quote)
        if len(quote_key) < 8:
            return None

        best_index: int | None = None
        best_score = 0
        for index, item in enumerate(qa_items, start=1):
            answer_key = self._match_key(str(item.get("answer", "")))
            if not answer_key:
                continue
            if quote_key in answer_key:
                score = len(quote_key)
            elif answer_key[: min(len(answer_key), 40)] in quote_key:
                score = min(len(answer_key), 40)
            else:
                score = 0
            if score > best_score:
                best_score = score
                best_index = index
        return best_index if best_score >= 8 else None

    def _match_key(self, text: str) -> str:
        return re.sub(r"\s+", "", text).lower()

    def _answer_excerpt(self, answer: str) -> str:
        compact = re.sub(r"\s+", " ", answer).strip()
        return compact[:90]

    def _is_partial_recovered(self, extraction: dict[str, Any]) -> bool:
        return "Recovered partial JSON" in str(extraction.get("_llm_error") or "")

    def _allowed_value(self, value: Any, allowed: set[str]) -> str:
        return value if isinstance(value, str) and value in allowed else "unknown"

    def _bounded_float(self, value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(1.0, number))

    def _heuristic_extract(self, text: str) -> dict[str, Any]:
        sentences = [s.strip() for s in re.split(r"[。！？!?；;\n]+", text) if s.strip()]
        # (keywords, element, dimension, indicator, macro_dichotomy, strength, valued, mental, accepting, contact, guide)
        rules = [
            (("未来", "可能", "潜力", "可能性", "隐含", "方向", "变化", "发展"), "Ne", "4D", "IND TM-A", "N",
             "strong", "valued", "mental", "accepting", "inert", "guide"),
            (("时间", "趋势", "预感", "走向", "长期", "过程", "进展"), "Ni", "4D", "IND TM-A", "N",
             "strong", "valued", "mental", "accepting", "inert", "guide"),
            (("空间", "力量", "控制", "边界", "压迫", "领地", "强势", "掌控"), "Se", "3D", "IND ST-A", "S",
             "strong", "valued", "mental", "producing", "contact", "separate"),
            (("身体", "舒适", "环境", "节奏", "适应", "感受", "体感", "细节"), "Si", "3D", "IND ST-A", "S",
             "strong", "valued", "mental", "accepting", "inert", "guide"),
            (("效率", "流程", "执行", "资源", "投入产出", "工具", "结果导向", "优化"), "Te", "3D", "IND ST-A", "T",
             "strong", "valued", "mental", "producing", "contact", "separate"),
            (("结构", "逻辑", "分类", "定义", "框架", "原则", "体系", "规律"), "Ti", "3D", "IND ST-A", "T",
             "strong", "valued", "mental", "accepting", "inert", "guide"),
            (("气氛", "情绪", "表达", "感染", "热场", "氛围", "共鸣", "活跃"), "Fe", "2D", "IND NR-D", "F",
             "weak", "valued", "mental", "producing", "contact", "separate"),
            (("关系", "距离", "亲近", "冒犯", "道德", "吸引", "排斥", "人际"), "Fi", "1D", "IND 1D-L", "F",
             "weak", "valued", "vital", "accepting", "inert", "guide"),
            # 2D/1D 弱点信号
            (("必须", "应该", "规范", "正确", "标准", "义务"), None, "2D", "IND NR-D", None,
             "weak", "unvalued", "mental", "unknown", "unknown", "unknown"),
            (("焦虑", "不知道怎么", "很难", "末日", "崩溃", "压力很大"), None, "1D", "IND LD-E", None,
             "weak", "unvalued", "unknown", "unknown", "unknown", "unknown"),
            # 生机环自动化信号
            (("有时候", "习惯", "自然而然", "不知不觉", "下意识"), None, "unknown", "IND VT-B", None,
             "unknown", "unknown", "vital", "unknown", "inert", "unknown"),
            # 4D 认同信号
            (("我就是这样", "天生", "一直如此", "本能", "游刃有余"), None, "4D", "IND F1-A", None,
             "strong", "valued", "unknown", "unknown", "unknown", "unknown"),
        ]
        quotes: list[dict[str, Any]] = []
        dichotomy_counts: dict[str, int] = {"N": 0, "S": 0, "T": 0, "F": 0, "E": 0, "I": 0}

        for sentence in sentences:
            for rule in rules:
                keywords, element, dimension, indicator, macro = rule[:5]
                strength, valued, mental, accepting, contact, guide = rule[5:]
                if any(keyword in sentence for keyword in keywords):
                    q: dict[str, Any] = {
                        "quote": sentence[:120],
                        "indicator": indicator,
                        "element_hint": element if element else "unknown",
                        "dimension_hint": dimension,
                        "position_hint": None,
                        "confidence": 0.5 if dimension in {"1D", "2D"} else 0.6,
                        "strength_signal": strength,
                        "valued_signal": valued,
                        "mental_signal": mental,
                        "accepting_signal": accepting,
                        "contact_signal": contact,
                        "guide_signal": guide,
                        "evidence_type": "keyword",
                        "reason": f"命中 {element or '?'} 相关行为词：{', '.join(keywords[:3])}",
                    }
                    quotes.append(q)
                    if macro:
                        dichotomy_counts[macro] += 1
                    if element and element in ELEMENT_GROUPS["E"]:
                        dichotomy_counts["E"] += 1
                    elif element and element in ELEMENT_GROUPS["I"]:
                        dichotomy_counts["I"] += 1
                    break
            if len(quotes) >= 20:
                break

        # 理性/非理性：看 T/F 类元素落在 accepting 还是 producing
        rational_accepting = sum(1 for q in quotes if q["element_hint"] in RATIONAL_ELEMENTS and q["accepting_signal"] == "accepting")
        irrational_accepting = sum(1 for q in quotes if q["element_hint"] in IRRATIONAL_ELEMENTS and q["accepting_signal"] == "accepting")
        if rational_accepting > irrational_accepting:
            r_lean, r_conf = "R", round((rational_accepting - irrational_accepting) / max(rational_accepting + irrational_accepting, 1), 2)
        elif irrational_accepting > rational_accepting:
            r_lean, r_conf = "Ir", round((irrational_accepting - rational_accepting) / max(rational_accepting + irrational_accepting, 1), 2)
        else:
            r_lean, r_conf = "unknown", 0.0

        def lean(a: str, b: str) -> dict[str, Any]:
            if dichotomy_counts[a] == dichotomy_counts[b]:
                return {"lean": "unknown", "confidence": 0.0, "evidence": []}
            winner = a if dichotomy_counts[a] > dichotomy_counts[b] else b
            total = dichotomy_counts[a] + dichotomy_counts[b]
            conf = abs(dichotomy_counts[a] - dichotomy_counts[b]) / max(total, 1)
            return {"lean": winner, "confidence": round(conf, 2), "evidence": []}

        insufficiency = []
        if len(quotes) < self.options.min_evidence:
            insufficiency.append("可用行为证据不足，建议补充具体场景、压力反应和合作方式。")

        return {
            "quotes": quotes,
            "dichotomy_signals": {
                "E_vs_I": lean("E", "I"),
                "N_vs_S": lean("N", "S"),
                "T_vs_F": lean("T", "F"),
                "R_vs_Ir": {"lean": r_lean, "confidence": r_conf, "evidence": []},
            },
            "laning_signals": {},
            "conflicts": [],
            "insufficiency": insufficiency,
        }

    def _score_candidates(self, extraction: dict[str, Any]) -> list[dict[str, Any]]:
        signal_summary = self._summarize_element_signals(extraction.get("quotes", []))
        raw_scores: dict[str, float] = {type_code: 0.0 for type_code in self.model_a}
        details: dict[str, dict[str, Any]] = {}
        max_possible = 2.0
        quotes = extraction.get("quotes", [])

        for type_code, meta in self.model_a.items():
            reverse_positions = self._positions_reverse(meta["model_a"])
            first_element = reverse_positions[1]
            second_element = reverse_positions[2]
            first_summary = signal_summary.get(first_element, {})
            second_summary = signal_summary.get(second_element, {})
            first_leading_support = self._position_profile_support(first_summary, 1)
            second_creative_support = self._position_profile_support(second_summary, 2)
            second_ignoring_risk = self._position_profile_support(second_summary, 7)
            first_4d_support = float(first_summary.get("4D", 0.0))
            first_axis_score = first_4d_support + 0.35 * first_leading_support

            raw_scores[type_code] += 1.2 * first_leading_support
            raw_scores[type_code] += 1.4 * second_creative_support
            raw_scores[type_code] -= 0.7 * second_ignoring_risk
            if first_4d_support <= 0:
                raw_scores[type_code] -= 1.2
            elif first_4d_support < 0.4:
                raw_scores[type_code] -= 0.6

            details[type_code] = {
                "first_hypothesis": first_element,
                "second_hypothesis": second_element,
                "first_4d_support": round(first_4d_support, 3),
                "first_axis_score": round(first_axis_score, 3),
                "second_3d_support": round(float(second_summary.get("3D", 0.0)), 3),
                "first_leading_support": round(first_leading_support, 3),
                "second_creative_support": round(second_creative_support, 3),
                "second_ignoring_risk": round(second_ignoring_risk, 3),
                "rule_matches": [],
                "rule_conflicts": [],
                "global_matches": [],
                "global_conflicts": [],
                "global_score": 0.0,
            }
            if second_ignoring_risk > second_creative_support and second_ignoring_risk >= 0.5:
                details[type_code]["rule_conflicts"].append(
                    f"{second_element} 更像 7th 忽略，而不是 2nd 创造"
                )
            global_score, global_matches, global_conflicts = self._global_model_checks(type_code, signal_summary)
            raw_scores[type_code] += global_score
            details[type_code]["global_score"] = round(global_score, 3)
            details[type_code]["global_matches"].extend(global_matches)
            details[type_code]["global_conflicts"].extend(global_conflicts)
            if self._rational_pair_is_valid(first_element, second_element):
                details[type_code]["rule_matches"].append("1st/2nd 满足理性+非理性搭配")
                raw_scores[type_code] += 0.4
            else:
                details[type_code]["rule_conflicts"].append("1st/2nd 不满足理性+非理性搭配")
                raw_scores[type_code] -= 1.0

        for item in quotes:
            element = item.get("element_hint")
            dimension = item.get("dimension_hint")
            position_hint = item.get("position_hint")
            strength_signal = item.get("strength_signal")
            valued_signal = item.get("valued_signal")
            mental_signal = item.get("mental_signal")
            accepting_signal = item.get("accepting_signal")
            contact_signal = item.get("contact_signal")
            guide_signal = item.get("guide_signal")
            confidence = float(item.get("confidence") or 0.5)
            if element not in {"Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi"}:
                continue
            max_possible += 3.8 * confidence
            for type_code, meta in self.model_a.items():
                positions = self._positions(meta["model_a"])
                position = positions[element]
                if dimension in DIMENSION_POSITIONS:
                    if position in DIMENSION_POSITIONS[dimension]:
                        raw_scores[type_code] += 1.4 * confidence
                        details[type_code]["rule_matches"].append(f"{element} 位置 {position} 匹配 {dimension}")
                    else:
                        penalty = self._dimension_mismatch_penalty(dimension, position) * confidence
                        raw_scores[type_code] -= penalty
                        if penalty >= 0.45:
                            details[type_code]["rule_conflicts"].append(
                                f"{element} 位置 {position} 与 {dimension} 证据冲突"
                            )
                if isinstance(position_hint, int) and position == position_hint:
                    raw_scores[type_code] += 0.6 * confidence
                if dimension == "4D" and position == 1:
                    raw_scores[type_code] += 0.35 * confidence
                if dimension == "1D" and position in {4, 5}:
                    raw_scores[type_code] += 0.35 * confidence
                if strength_signal in {"strong", "weak"}:
                    if (strength_signal == "strong" and position in STRONG_POSITIONS) or (
                        strength_signal == "weak" and position not in STRONG_POSITIONS
                    ):
                        raw_scores[type_code] += 0.3 * confidence
                    else:
                        raw_scores[type_code] -= 0.35 * confidence
                        details[type_code]["rule_conflicts"].append(
                            f"{element} 强弱信号 {strength_signal} 与位置 {position} 不一致"
                        )
                if valued_signal in {"valued", "unvalued"}:
                    if (valued_signal == "valued" and position in VALUED_POSITIONS) or (
                        valued_signal == "unvalued" and position not in VALUED_POSITIONS
                    ):
                        raw_scores[type_code] += 0.25 * confidence
                    else:
                        raw_scores[type_code] -= 0.4 * confidence
                        details[type_code]["rule_conflicts"].append(
                            f"{element} 重视信号 {valued_signal} 与位置 {position} 不一致"
                        )
                if mental_signal in {"mental", "vital"}:
                    if (mental_signal == "mental" and position in MENTAL_POSITIONS) or (
                        mental_signal == "vital" and position not in MENTAL_POSITIONS
                    ):
                        raw_scores[type_code] += 0.2 * confidence
                    else:
                        raw_scores[type_code] -= 0.25 * confidence
                if accepting_signal in {"accepting", "producing"}:
                    if (accepting_signal == "accepting" and position in ACCEPTING_POSITIONS) or (
                        accepting_signal == "producing" and position in PRODUCING_POSITIONS
                    ):
                        raw_scores[type_code] += 0.25 * confidence
                    else:
                        raw_scores[type_code] -= 0.35 * confidence
                        details[type_code]["rule_conflicts"].append(
                            f"{element} 接受/生产信号 {accepting_signal} 与位置 {position} 不一致"
                        )
                if contact_signal in {"contact", "inert"}:
                    if (contact_signal == "contact" and position in CONTACT_POSITIONS) or (
                        contact_signal == "inert" and position in INERT_POSITIONS
                    ):
                        raw_scores[type_code] += 0.15 * confidence
                if guide_signal in {"guide", "separate"}:
                    if (guide_signal == "guide" and position in GUIDE_POSITIONS) or (
                        guide_signal == "separate" and position in SEPARATE_POSITIONS
                    ):
                        raw_scores[type_code] += 0.15 * confidence

        # IND 行为指标积分：每条 quote 的 indicator 若命中 IND_PROFILES，则补充缺失信号后再走评分
        for item in quotes:
            indicator = item.get("indicator", "")
            profile = IND_PROFILES.get(indicator)
            if not profile:
                continue
            element = item.get("element_hint")
            if element not in {"Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi"}:
                continue
            confidence = float(item.get("confidence") or 0.5)
            # 用 IND profile 补充当条证据缺失的信号，并给候选类型加分
            for type_code, meta in self.model_a.items():
                positions = self._positions(meta["model_a"])
                position = positions[element]
                ind_score = 0.0
                # dimension_hint 补充分
                ind_dim = profile.get("dimension_hint")
                if ind_dim and ind_dim in DIMENSION_POSITIONS:
                    if position in DIMENSION_POSITIONS[ind_dim]:
                        ind_score += 0.5 * confidence
                    else:
                        ind_score -= self._dimension_mismatch_penalty(ind_dim, position) * 0.4 * confidence
                # strength_signal 补充分
                ind_str = profile.get("strength_signal")
                if ind_str in {"strong", "weak"}:
                    if (ind_str == "strong" and position in STRONG_POSITIONS) or (
                        ind_str == "weak" and position not in STRONG_POSITIONS
                    ):
                        ind_score += 0.2 * confidence
                    else:
                        ind_score -= 0.25 * confidence
                # valued_signal 补充分
                ind_val = profile.get("valued_signal")
                if ind_val in {"valued", "unvalued"}:
                    if (ind_val == "valued" and position in VALUED_POSITIONS) or (
                        ind_val == "unvalued" and position not in VALUED_POSITIONS
                    ):
                        ind_score += 0.15 * confidence
                    else:
                        ind_score -= 0.2 * confidence
                # mental_signal 补充分
                ind_men = profile.get("mental_signal")
                if ind_men in {"mental", "vital"}:
                    if (ind_men == "mental" and position in MENTAL_POSITIONS) or (
                        ind_men == "vital" and position not in MENTAL_POSITIONS
                    ):
                        ind_score += 0.12 * confidence
                    else:
                        ind_score -= 0.15 * confidence
                raw_scores[type_code] += ind_score

        dichotomy_scores = extraction.get("dichotomy_signals", {})
        for key, signal in dichotomy_scores.items():
            lean = signal.get("lean") if isinstance(signal, dict) else None
            confidence = float(signal.get("confidence") or 0.0) if isinstance(signal, dict) else 0.0
            if lean not in ELEMENT_GROUPS or confidence <= 0:
                continue
            max_possible += confidence
            for type_code, meta in self.model_a.items():
                first_element = self._positions_reverse(meta["model_a"])[1]
                if first_element in ELEMENT_GROUPS[lean]:
                    raw_scores[type_code] += 0.8 * confidence

        ranked = []
        for type_code, score in raw_scores.items():
            normalized = max(0.0, min(1.0, score / max_possible + 0.2))
            rule_conflicts = self._dedupe(details[type_code]["rule_conflicts"])
            rule_matches = self._dedupe(details[type_code]["rule_matches"])
            if details[type_code]["first_4d_support"] <= 0:
                normalized = min(normalized, 0.58)
            ranked.append(
                {
                    "type": type_code,
                    "score": round(normalized, 3),
                    "first_hypothesis": details[type_code]["first_hypothesis"],
                    "second_hypothesis": details[type_code]["second_hypothesis"],
                    "first_4d_support": details[type_code]["first_4d_support"],
                    "first_axis_score": details[type_code]["first_axis_score"],
                    "second_3d_support": details[type_code]["second_3d_support"],
                    "first_leading_support": details[type_code]["first_leading_support"],
                    "second_creative_support": details[type_code]["second_creative_support"],
                    "second_ignoring_risk": details[type_code]["second_ignoring_risk"],
                    "rule_matches": rule_matches[:8],
                    "rule_conflicts": rule_conflicts[:8],
                    "global_score": details[type_code]["global_score"],
                    "global_matches": self._dedupe(details[type_code]["global_matches"])[:8],
                    "global_conflicts": self._dedupe(details[type_code]["global_conflicts"])[:8],
                    "hard_conflict_count": len(rule_conflicts),
                }
            )
        return sorted(
            ranked,
            key=lambda item: (
                item["first_4d_support"] > 0,
                item["first_axis_score"],
                item["score"],
            ),
            reverse=True,
        )

    def _global_model_checks(self, type_code: str, summary: dict[str, dict[str, float]]) -> tuple[float, list[str], list[str]]:
        meta = self.model_a[type_code]
        positions = self._positions(meta["model_a"])
        reverse_positions = self._positions_reverse(meta["model_a"])
        first = reverse_positions[1]
        score = 0.0
        matches: list[str] = []
        conflicts: list[str] = []

        score += self._check_position_axis(
            summary, positions, "接受/生产", "accepting", "producing", ACCEPTING_POSITIONS, PRODUCING_POSITIONS, matches, conflicts
        )
        score += self._check_position_axis(
            summary, positions, "接触/惰性", "contact", "inert", CONTACT_POSITIONS, INERT_POSITIONS, matches, conflicts
        )
        score += self._check_position_axis(
            summary, positions, "引导/分离", "guide", "separate", GUIDE_POSITIONS, SEPARATE_POSITIONS, matches, conflicts
        )

        static_dynamic_score, static_dynamic_matches, static_dynamic_conflicts = self._check_static_dynamic(
            type_code, summary
        )
        score += static_dynamic_score
        matches.extend(static_dynamic_matches)
        conflicts.extend(static_dynamic_conflicts)

        rational_score, rational_matches, rational_conflicts = self._check_rational_model(first, summary)
        score += rational_score
        matches.extend(rational_matches)
        conflicts.extend(rational_conflicts)

        return score, self._dedupe(matches), self._dedupe(conflicts)

    def _check_position_axis(
        self,
        summary: dict[str, dict[str, float]],
        positions: dict[str, int],
        label: str,
        positive_key: str,
        negative_key: str,
        positive_positions: set[int],
        negative_positions: set[int],
        matches: list[str],
        conflicts: list[str],
    ) -> float:
        score = 0.0
        for element, values in summary.items():
            positive = float(values.get(positive_key, 0.0))
            negative = float(values.get(negative_key, 0.0))
            if max(positive, negative) < 0.35:
                continue
            position = positions[element]
            if positive > negative:
                if position in positive_positions:
                    score += 0.22 * positive
                    matches.append(f"{label}: {element} 符合 {positive_key}")
                else:
                    score -= 0.35 * positive
                    conflicts.append(f"{label}: {element} 的 {positive_key} 与 {position} 位冲突")
            elif negative > positive:
                if position in negative_positions:
                    score += 0.22 * negative
                    matches.append(f"{label}: {element} 符合 {negative_key}")
                else:
                    score -= 0.35 * negative
                    conflicts.append(f"{label}: {element} 的 {negative_key} 与 {position} 位冲突")
        return score

    def _check_static_dynamic(self, type_code: str, summary: dict[str, dict[str, float]]) -> tuple[float, list[str], list[str]]:
        mental_static = sum(summary[element]["mental"] for element in STATIC_ELEMENTS)
        mental_dynamic = sum(summary[element]["mental"] for element in DYNAMIC_ELEMENTS)
        vital_static = sum(summary[element]["vital"] for element in STATIC_ELEMENTS)
        vital_dynamic = sum(summary[element]["vital"] for element in DYNAMIC_ELEMENTS)
        score = 0.0
        matches: list[str] = []
        conflicts: list[str] = []
        if type_code in STATIC_TYPES:
            support = mental_static + vital_dynamic
            tension = mental_dynamic + vital_static
            if support >= 0.4:
                score += 0.18 * support
                matches.append("静态/动态: 符合静态类型环路")
            if tension >= 0.4:
                score -= 0.28 * tension
                conflicts.append("静态/动态: 与静态类型环路有张力")
        elif type_code in DYNAMIC_TYPES:
            support = mental_dynamic + vital_static
            tension = mental_static + vital_dynamic
            if support >= 0.4:
                score += 0.18 * support
                matches.append("静态/动态: 符合动态类型环路")
            if tension >= 0.4:
                score -= 0.28 * tension
                conflicts.append("静态/动态: 与动态类型环路有张力")
        return score, matches, conflicts

    def _check_rational_model(self, first: str, summary: dict[str, dict[str, float]]) -> tuple[float, list[str], list[str]]:
        accepting_rational = sum(summary[element]["accepting"] for element in RATIONAL_ELEMENTS)
        accepting_irrational = sum(summary[element]["accepting"] for element in IRRATIONAL_ELEMENTS)
        producing_rational = sum(summary[element]["producing"] for element in RATIONAL_ELEMENTS)
        producing_irrational = sum(summary[element]["producing"] for element in IRRATIONAL_ELEMENTS)
        score = 0.0
        matches: list[str] = []
        conflicts: list[str] = []
        if first in RATIONAL_ELEMENTS:
            support = accepting_rational + producing_irrational
            tension = accepting_irrational + producing_rational
            if support >= 0.4:
                score += 0.2 * support
                matches.append("理性/非理性整模型: 支持理性类型")
            if tension >= 0.4:
                score -= 0.32 * tension
                conflicts.append("理性/非理性整模型: 与理性类型有张力")
        else:
            support = accepting_irrational + producing_rational
            tension = accepting_rational + producing_irrational
            if support >= 0.4:
                score += 0.2 * support
                matches.append("理性/非理性整模型: 支持非理性类型")
            if tension >= 0.4:
                score -= 0.32 * tension
                conflicts.append("理性/非理性整模型: 与非理性类型有张力")
        return score, matches, conflicts

    def _summarize_element_signals(self, quotes: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        summary: dict[str, dict[str, float]] = {
            element: {
                "1D": 0.0,
                "2D": 0.0,
                "3D": 0.0,
                "4D": 0.0,
                "strong": 0.0,
                "weak": 0.0,
                "valued": 0.0,
                "unvalued": 0.0,
                "mental": 0.0,
                "vital": 0.0,
                "accepting": 0.0,
                "producing": 0.0,
                "contact": 0.0,
                "inert": 0.0,
                "guide": 0.0,
                "separate": 0.0,
            }
            for element in {"Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi"}
        }
        for item in quotes:
            element = item.get("element_hint")
            if element not in summary:
                continue
            confidence = float(item.get("confidence") or 0.5)
            dimension = item.get("dimension_hint")
            if dimension in {"1D", "2D", "3D", "4D"}:
                summary[element][dimension] += confidence
            strength = item.get("strength_signal")
            if strength in {"strong", "weak"}:
                summary[element][strength] += confidence
            valued = item.get("valued_signal")
            if valued in {"valued", "unvalued"}:
                summary[element][valued] += confidence
            mental = item.get("mental_signal")
            if mental in {"mental", "vital"}:
                summary[element][mental] += confidence
            accepting = item.get("accepting_signal")
            if accepting in {"accepting", "producing"}:
                summary[element][accepting] += confidence
            contact = item.get("contact_signal")
            if contact in {"contact", "inert"}:
                summary[element][contact] += confidence
            guide = item.get("guide_signal")
            if guide in {"guide", "separate"}:
                summary[element][guide] += confidence
        return summary

    def _rational_pair_is_valid(self, first: str, second: str) -> bool:
        return (first in RATIONAL_ELEMENTS and second in IRRATIONAL_ELEMENTS) or (
            first in IRRATIONAL_ELEMENTS and second in RATIONAL_ELEMENTS
        )

    def _position_profile_support(self, summary: dict[str, float], position: int) -> float:
        profiles = {
            1: {
                "4D": 1.2,
                "strong": 0.4,
                "valued": 0.7,
                "mental": 0.5,
                "accepting": 0.4,
                "inert": 0.25,
                "guide": 0.2,
            },
            2: {
                "3D": 1.0,
                "strong": 0.35,
                "valued": 0.9,
                "mental": 0.55,
                "producing": 0.55,
                "contact": 0.35,
                "separate": 0.2,
            },
            7: {
                "3D": 0.8,
                "strong": 0.3,
                "unvalued": 0.9,
                "vital": 0.55,
                "accepting": 0.55,
                "inert": 0.35,
                "separate": 0.2,
            },
            8: {
                "4D": 0.9,
                "strong": 0.35,
                "unvalued": 0.8,
                "vital": 0.45,
                "producing": 0.45,
                "contact": 0.25,
                "guide": 0.2,
            },
        }
        return sum(float(summary.get(key, 0.0)) * weight for key, weight in profiles[position].items())

    def _dimension_mismatch_penalty(self, dimension: str, position: int) -> float:
        if dimension == "4D":
            return 0.9 if position in {3, 4, 5, 6} else 0.35
        if dimension == "3D":
            return 0.65 if position in {4, 5} else 0.25
        if dimension == "2D":
            return 0.55 if position in {1, 8} else 0.25
        if dimension == "1D":
            return 0.9 if position in {1, 2, 7, 8} else 0.25
        return 0.25

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        result = []
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result

    def _positions(self, model_a: list[str]) -> dict[str, int]:
        return {slot[1:]: int(slot[0]) for slot in model_a}

    def _positions_reverse(self, model_a: list[str]) -> dict[int, str]:
        return {int(slot[0]): slot[1:] for slot in model_a}

    def _build_result(
        self,
        case_id: str,
        candidates: list[dict[str, Any]],
        extraction: dict[str, Any],
        prepared: dict[str, Any],
    ) -> dict[str, Any]:
        top = candidates[0] if candidates else {"type": None, "score": 0.0}
        second = candidates[1] if len(candidates) > 1 else {"score": 0.0}
        evidence_count = len(extraction.get("quotes", []))
        conflicts = extraction.get("conflicts", [])
        insufficiency = extraction.get("insufficiency", [])

        laning_signals = extraction.get("laning_signals", {})
        laning_result: dict[str, Any] | None = None

        margin_small = top["score"] - second["score"] < self.options.margin_threshold
        score_low = top["score"] < self.options.top_threshold
        no_4d = top.get("first_4d_support", 0.0) < 0.4
        no_3d = top.get("second_3d_support", 0.0) < 0.4
        creative_confused = top.get("second_creative_support", 0.0) <= top.get("second_ignoring_risk", 0.0)
        few_evidence = evidence_count < self.options.min_evidence

        # 只有 dimension 类冲突（同元素同时像 1D/4D）才是真实不确定；signal 类（信号方向误判）不阻塞赖宁决断
        real_conflicts = [c for c in conflicts if isinstance(c, dict) and c.get("conflict_kind") != "signal"]
        partial_recovered = self._is_partial_recovered(extraction)
        schema_invalid = bool(extraction.get("_schema_invalid"))
        hard_uncertain = no_4d or no_3d or few_evidence or bool(real_conflicts) or partial_recovered or schema_invalid

        if not hard_uncertain and margin_small and not score_low and not creative_confused and not insufficiency:
            # 仅 margin 不足：先试赖宁决断
            laning_result = self._laning_tiebreak(candidates, laning_signals)
            if laning_result:
                top = laning_result["winner"]
                status = "certain"
            else:
                status = "uncertain"
        elif score_low or hard_uncertain or creative_confused or insufficiency:
            status = "uncertain"
        else:
            status = "certain"

        type_code = top["type"] if status == "certain" else None
        meta = self.model_a.get(top["type"], {})
        return {
            "case_id": case_id,
            "status": status,
            "type": type_code,
            "alias": meta.get("alias") if type_code else None,
            "quadra": meta.get("quadra") if type_code else None,
            "confidence": min(top["score"], 0.74) if partial_recovered else top["score"],
            "candidates": candidates[:3],
            "candidate_explanations": self._explain_candidates(candidates[:3], extraction),
            "model_a": meta.get("model_a", []) if type_code else [],
            "evidence_chain": extraction.get("quotes", []),
            "preprocess": {
                "mode": prepared["mode"],
                "source": prepared.get("source", "raw_text"),
                "qa_count": prepared["qa_count"],
                "original_length": prepared["original_length"],
                "analysis_length": prepared["analysis_length"],
                "qa_items": prepared["qa_items"][:10],
            },
            "input_encoding": "utf-8",
            "extraction_source": extraction.get("_source", "unknown"),
            "llm_error": extraction.get("_llm_error"),
            "llm_raw_path": extraction.get("_llm_raw_path"),
            "llm_request": extraction.get("_llm_request"),
            "schema_invalid": schema_invalid,
            "dichotomy_signals": extraction.get("dichotomy_signals", {}),
            "laning_signals": laning_signals,
            "laning_tiebreak": laning_result,
            "conflicts": conflicts,
            "insufficiency": insufficiency,
            "uncertainty_reasons": self._uncertainty_reasons(top, second, evidence_count, conflicts, insufficiency, laning_result),
            "refinement": None,
            "synthesis_pass": None,
            "arbitration": None,
            "clarification_request": None,
            "report": "",
        }

    def _explain_candidates(
        self, candidates: list[dict[str, Any]], extraction: dict[str, Any]
    ) -> list[dict[str, Any]]:
        explanations = []
        for candidate in candidates:
            type_code = candidate["type"]
            meta = self.model_a[type_code]
            positions = self._positions(meta["model_a"])
            matched: list[str] = []
            tension: list[str] = []
            for item in extraction.get("quotes", [])[:10]:
                element = item.get("element_hint")
                dimension = item.get("dimension_hint")
                if element not in positions:
                    continue
                position = positions[element]
                quote = item.get("quote", "")[:28]
                if dimension in DIMENSION_POSITIONS and position in DIMENSION_POSITIONS[dimension]:
                    matched.append(f"{element} 在 {position} 位匹配 {dimension}: {quote}")
                elif dimension in DIMENSION_POSITIONS:
                    tension.append(f"{element} 在 {position} 位不匹配 {dimension}: {quote}")
            explanations.append(
                {
                    "type": type_code,
                    "score": candidate["score"],
                    "first_hypothesis": candidate.get("first_hypothesis"),
                    "second_hypothesis": candidate.get("second_hypothesis"),
                    "first_4d_support": candidate.get("first_4d_support", 0.0),
                    "first_axis_score": candidate.get("first_axis_score", 0.0),
                    "second_3d_support": candidate.get("second_3d_support", 0.0),
                    "second_creative_support": candidate.get("second_creative_support", 0.0),
                    "second_ignoring_risk": candidate.get("second_ignoring_risk", 0.0),
                    "matched": matched[:4],
                    "tension": tension[:3],
                    "rule_matches": candidate.get("rule_matches", [])[:4],
                    "rule_conflicts": candidate.get("rule_conflicts", [])[:4],
                    "global_score": candidate.get("global_score", 0.0),
                    "global_matches": candidate.get("global_matches", [])[:4],
                    "global_conflicts": candidate.get("global_conflicts", [])[:4],
                }
            )
        return explanations

    def _uncertainty_reasons(
        self,
        top: dict[str, Any],
        second: dict[str, Any],
        evidence_count: int,
        conflicts: list[Any],
        insufficiency: list[Any],
        laning_result: dict[str, Any] | None = None,
    ) -> list[str]:
        reasons = []
        if top["score"] < self.options.top_threshold:
            reasons.append(f"最高分 {top['score']:.3f} 低于确定阈值 {self.options.top_threshold:.2f}。")
        margin = top["score"] - second["score"]
        if margin < self.options.margin_threshold:
            if laning_result:
                reasons.append(
                    f"前两名分差 {margin:.3f} 小于阈值，已由赖宁二分法决断为 {laning_result['winner']['type']}。"
                    f"（{'; '.join(laning_result.get('used_signals', []))}）"
                )
            else:
                reasons.append(f"前两名分差 {margin:.3f} 小于 {self.options.margin_threshold:.2f}，赖宁信号不足无法决断。")
        if top.get("first_4d_support", 0.0) < 0.4:
            reasons.append(f"未锁定 4D 主导：{top.get('first_hypothesis')} 的 4D 证据不足。")
        if top.get("second_3d_support", 0.0) < 0.4:
            reasons.append(f"未锁定 3D 创造：{top.get('second_hypothesis')} 的 3D 证据不足。")
        if top.get("second_creative_support", 0.0) <= top.get("second_ignoring_risk", 0.0):
            reasons.append(
                f"创造/忽略未分清：{top.get('second_hypothesis')} 的 2nd 创造支持 "
                f"{top.get('second_creative_support', 0.0):.3f}，7th 忽略风险 "
                f"{top.get('second_ignoring_risk', 0.0):.3f}。"
            )
        if top.get("hard_conflict_count", 0) > 0:
            reasons.append(f"最高候选存在 {top.get('hard_conflict_count')} 条硬规则冲突。")
        if top.get("global_conflicts"):
            reasons.append("七大二分法全局校验存在张力：" + "；".join(top.get("global_conflicts", [])[:2]))
        if evidence_count < self.options.min_evidence:
            reasons.append(f"有效证据 {evidence_count} 条，少于 {self.options.min_evidence} 条。")
        real_conflicts = [c for c in conflicts if isinstance(c, dict) and c.get("conflict_kind") != "signal"]
        signal_conflicts = [c for c in conflicts if isinstance(c, dict) and c.get("conflict_kind") == "signal"]
        if real_conflicts:
            reasons.append(f"存在 {len(real_conflicts)} 条维度矛盾冲突（同元素在不同题目中表现差异极大）。")
        if signal_conflicts:
            reasons.append(f"存在 {len(signal_conflicts)} 条信号方向疑似误判（不阻塞决断，仅供参考）。")
        if insufficiency:
            reasons.extend(str(item) for item in insufficiency)
        return reasons

    def _identify_blocking_axis(
        self,
        candidates: list[dict[str, Any]],
        uncertainty_reasons: list[str],
        extraction: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        识别阻塞判型的核心轴，返回 {"axis", "competing_types", "missing_elements", "blocking_reason"}。
        决策树优先级：
        1. top-2 同 1st、2nd 不同 → 2nd 元素对（LIE/LSE → Ni_vs_Si）
        2. top-2 1st 不同 → 1st 元素对
        3. second_3d_support == 0 → 2nd_vs_7th
        4. dimension 类 real conflict → 冲突元素对
        """
        if len(candidates) < 2:
            return None
        top, second = candidates[0], candidates[1]
        top_1st = top.get("first_hypothesis", "")
        top_2nd = top.get("second_hypothesis", "")
        sec_1st = second.get("first_hypothesis", "")
        sec_2nd = second.get("second_hypothesis", "")
        competing = [top["type"], second["type"]]

        # 情况 1：共享同一 1st，2nd 不同（如 LIE=Te-Ni vs LSE=Te-Si）
        if top_1st and top_1st == sec_1st and top_2nd and sec_2nd and top_2nd != sec_2nd:
            pair = frozenset({top_2nd, sec_2nd})
            axis = ELEMENT_PAIR_TO_AXIS.get(pair)
            if axis:
                return {
                    "axis": axis,
                    "axis_description": AXIS_DESCRIPTIONS.get(axis, axis),
                    "competing_types": competing,
                    "missing_elements": sorted({top_2nd, sec_2nd}),
                    "blocking_reason": f"{competing[0]} 和 {competing[1]} 共享 1st={top_1st}，区分钥匙是 2nd：{top_2nd} vs {sec_2nd}，但当前证据缺少这两个元素。",
                }

        # 情况 2：1st 不同
        if top_1st and sec_1st and top_1st != sec_1st:
            pair = frozenset({top_1st, sec_1st})
            axis = ELEMENT_PAIR_TO_AXIS.get(pair)
            if axis:
                return {
                    "axis": axis,
                    "axis_description": AXIS_DESCRIPTIONS.get(axis, axis),
                    "competing_types": competing,
                    "missing_elements": sorted({top_1st, sec_1st}),
                    "blocking_reason": f"主导功能假设分歧：{competing[0]}={top_1st} vs {competing[1]}={sec_1st}，需要更强的 1st 功能证据。",
                }

        # 情况 3：2nd 功能 3D 证据为 0，无法区分创造 vs 忽略
        if top.get("second_3d_support", 0.0) == 0.0:
            return {
                "axis": "2nd_vs_7th",
                "axis_description": AXIS_DESCRIPTIONS.get("2nd_vs_7th", "2nd_vs_7th"),
                "competing_types": competing,
                "missing_elements": [top_2nd] if top_2nd else [],
                "blocking_reason": f"无法判断 {top_2nd} 是 2nd 创造（主动/重视）还是 7th 忽略（强但厌倦/非重视）。",
            }

        # 情况 4：有 dimension 类真实冲突，提取冲突元素对
        for conflict in extraction.get("conflicts", []):
            if not isinstance(conflict, dict) or conflict.get("conflict_kind") != "dimension":
                continue
            topic = conflict.get("topic", "")
            if " vs " in topic:
                parts = topic.split(" vs ")
                elem1, elem2 = parts[0].strip(), parts[1].strip()
                pair = frozenset({elem1, elem2})
                axis = ELEMENT_PAIR_TO_AXIS.get(pair)
                if axis:
                    return {
                        "axis": axis,
                        "axis_description": AXIS_DESCRIPTIONS.get(axis, axis),
                        "competing_types": competing,
                        "missing_elements": sorted({elem1, elem2}),
                        "blocking_reason": f"维度冲突：{conflict.get('reason', topic)}",
                    }

        return None

    def _synthesize_evidence(
        self,
        raw_extraction: dict[str, Any],
        prepared: dict[str, Any],
    ) -> dict[str, Any] | None:
        """阶段 2：LLM 输出结构化维度决策表，Python 按决策表重打标签并筛选 8 条核心证据。"""
        prompt_path = BASE_DIR / "prompts" / "evidence_synthesis.md"
        if not prompt_path.exists():
            return None
        if not self.llm.config.enabled:
            return None
        raw_quotes = raw_extraction.get("quotes", [])
        if len(raw_quotes) <= 8:
            return None  # 无需精炼

        system_prompt = prompt_path.read_text(encoding="utf-8")
        raw_quotes_json = json.dumps(raw_quotes, ensure_ascii=False)
        text_excerpt = prepared.get("analysis_text", "")[:1500]
        if prepared.get("mode") == "qa_answers_only":
            text_label = "问卷回答节选"
        else:
            text_label = "用户文本节选"

        user_prompt = (
            f"【原始证据池（{len(raw_quotes)} 条）】\n{raw_quotes_json}\n\n"
            f"【{text_label}】\n{text_excerpt}\n\n"
            f"请为每个元素判定最终维度，输出 JSON。"
        )

        decision = self.llm.chat_json(system_prompt, user_prompt)
        if not isinstance(decision, dict) or "element_dimensions" not in decision:
            return None

        # 用决策表重打标签
        element_dim_map: dict[str, str] = {}
        element_dim_rationale: dict[str, str] = {}
        for elem, info in decision["element_dimensions"].items():
            if elem in {"Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi"} and isinstance(info, dict):
                dim = info.get("dimension")
                if dim in {"1D", "2D", "3D", "4D"}:
                    element_dim_map[elem] = dim
                    element_dim_rationale[elem] = info.get("rationale", "")

        # 对原始证据池重打 dimension_hint 标签
        relabeled_quotes: list[dict[str, Any]] = []
        for q in raw_extraction["quotes"]:
            elem = q.get("element_hint")
            if elem in element_dim_map:
                new_q = dict(q)
                if new_q.get("dimension_hint") != element_dim_map[elem]:
                    new_q["_original_dimension"] = new_q.get("dimension_hint")
                new_q["dimension_hint"] = element_dim_map[elem]
                relabeled_quotes.append(new_q)
            else:
                relabeled_quotes.append(dict(q))

        # 代码侧筛选 8 条
        target_count = self._evidence_target_count(prepared)
        final_quotes = self._select_final_quotes(relabeled_quotes, target_count=target_count, prepared=prepared)

        return {
            "quotes": final_quotes,
            "_source": "llm_synthesized",
            "_element_dimensions": element_dim_map,
            "_dimension_rationale": element_dim_rationale,
            "_synthesis_notes": decision.get("synthesis_notes", ""),
            "_raw_quote_count": len(raw_quotes),
            "_llm_error": raw_extraction.get("_llm_error"),
            "_llm_raw_path": raw_extraction.get("_llm_raw_path"),
            "dichotomy_signals": raw_extraction.get("dichotomy_signals", {}),
            "laning_signals": raw_extraction.get("laning_signals", {}),
            "conflicts": raw_extraction.get("conflicts", []),
            "insufficiency": raw_extraction.get("insufficiency", []),
        }

    def _evidence_target_count(self, prepared: dict[str, Any]) -> int:
        if prepared.get("mode") == "qa_answers_only":
            return min(30, max(8, int(prepared.get("qa_count") or 0)))
        return 8

    def _quote_priority(self, q: dict[str, Any]) -> float:
        ind_bonus = 1.5 if str(q.get("indicator", "")).startswith("IND") else 1.0
        conf = float(q.get("confidence") or 0.5)
        coverage_bonus = 0.25 if q.get("qa_index") is not None else 0.0
        fallback_penalty = -0.2 if q.get("_coverage_fallback") else 0.0
        return ind_bonus * conf + coverage_bonus + fallback_penalty

    def _select_final_quotes(
        self,
        quotes: list[dict[str, Any]],
        target_count: int = 8,
        prepared: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """代码侧鱼谪技：按元素分组，IND 命中优先，每组最多 2 条，先凑覆盖再补高分。"""
        from collections import defaultdict
        quotes = self._attach_qa_context_to_quotes(quotes, prepared or {})
        if prepared and prepared.get("mode") == "qa_answers_only":
            by_qa: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for q in quotes:
                qa_index = q.get("qa_index")
                if isinstance(qa_index, int):
                    by_qa[qa_index].append(q)

            selected_by_qa: list[dict[str, Any]] = []
            selected_ids: set[int] = set()
            for qa_index in sorted(by_qa):
                best = sorted(by_qa[qa_index], key=self._quote_priority, reverse=True)[0]
                selected_by_qa.append(best)
                selected_ids.add(id(best))

            leftovers_by_qa = [q for q in quotes if id(q) not in selected_ids]
            leftovers_by_qa.sort(key=self._quote_priority, reverse=True)
            if len(selected_by_qa) < target_count:
                selected_by_qa.extend(leftovers_by_qa[: target_count - len(selected_by_qa)])
            selected_by_qa.sort(key=lambda q: (q.get("qa_index") is None, q.get("qa_index") or 0, -self._quote_priority(q)))
            return selected_by_qa[:target_count]

        by_element: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for q in quotes:
            elem = q.get("element_hint", "unknown")
            by_element[elem].append(q)

        def priority(q: dict[str, Any]) -> float:
            ind_bonus = 1.5 if str(q.get("indicator", "")).startswith("IND") else 1.0
            conf = float(q.get("confidence") or 0.5)
            return ind_bonus * conf

        # 每组内排序，取最多 2 条
        selected: list[dict[str, Any]] = []
        leftovers: list[dict[str, Any]] = []
        for elem, group in by_element.items():
            sorted_group = sorted(group, key=priority, reverse=True)
            selected.extend(sorted_group[:2])
            leftovers.extend(sorted_group[2:])

        # 若超过 target_count，按 priority 截断
        if len(selected) > target_count:
            selected.sort(key=priority, reverse=True)
            return selected[:target_count]

        # 若不足，从 leftovers 补高分
        if len(selected) < target_count and leftovers:
            leftovers.sort(key=priority, reverse=True)
            needed = target_count - len(selected)
            selected.extend(leftovers[:needed])

        # 最终按 priority 排序（信息密度高的在前）
        selected.sort(key=priority, reverse=True)
        return selected

    def _build_l1_request(
        self,
        prepared: dict[str, Any],
        blocking_axis: dict[str, Any],
        existing_extraction: dict[str, Any] | None = None,
    ) -> tuple[str, str] | None:
        """构造 L1 定向重提取的 (system_prompt, user_prompt)。"""
        prompt_path = BASE_DIR / "prompts" / "directed_extraction.md"
        if not prompt_path.exists():
            return None
        system_prompt = prompt_path.read_text(encoding="utf-8")

        axis_desc = blocking_axis.get("axis_description", blocking_axis.get("axis", ""))
        missing = blocking_axis.get("missing_elements", [])
        competing = blocking_axis.get("competing_types", [])
        full_text = prepared.get("analysis_text", "")

        if prepared.get("mode") == "qa_answers_only":
            text_label = "问卷回答"
        else:
            text_label = "用户文本"

        # 注入已锁定的维度判定（防漂移）
        locked_dims: dict[str, str] = {}
        if existing_extraction:
            for q in existing_extraction.get("quotes", []):
                elem = q.get("element_hint", "")
                dim = q.get("dimension_hint", "")
                if elem not in {"unknown", None} and dim in {"1D", "2D", "3D", "4D"}:
                    existing = locked_dims.get(elem, "")
                    if dim > existing:
                        locked_dims[elem] = dim

        user_prompt = (
            f"当前判型卡在：{axis_desc}\n"
            f"竞争类型：{', '.join(competing)}\n"
            f"需要重点寻找的元素证据：{', '.join(missing)}\n\n"
            f"请重新通读以下{text_label}，专门补充与上述元素相关的新证据。"
            f"只输出与阻塞轴相关的新发现的 quotes（3-6 条），不重复已有证据。只输出 JSON。\n\n"
            f"{text_label}：\n{full_text}"
        )
        if locked_dims:
            user_prompt += f"\n\n【已锁定的维度判定，不可修改】\n{json.dumps(locked_dims, ensure_ascii=False)}"

        return system_prompt, user_prompt

    def _is_valid_directed_quote(self, quote: dict[str, Any], blocking_axis: dict[str, Any]) -> bool:
        """L1 directed evidence is allowed to refine only when it carries a real IND marker."""
        indicator = str(quote.get("indicator", ""))
        if indicator not in IND_PROFILES:
            return False
        element = quote.get("element_hint")
        if element not in {"Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi"}:
            return False
        missing = set(blocking_axis.get("missing_elements") or [])
        if missing and element not in missing:
            return False
        return True

    def _apply_directed_reextract(
        self,
        result: dict[str, Any],
        extraction: dict[str, Any],
        candidates: list[dict[str, Any]],
        prepared: dict[str, Any],
        case_id: str,
        blocking_axis: dict[str, Any],
        llm_raw_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """把 L1 LLM 返回的原始结果应用到证据池，合并、去漂移、重新打分。"""
        if not llm_raw_result or not self._is_valid_extraction(llm_raw_result):
            return {"_result": result, "_extraction": extraction, "_candidates": candidates}
        extra = self._normalize_extraction(llm_raw_result)
        extra["quotes"] = [
            q for q in extra.get("quotes", [])
            if self._is_valid_directed_quote(q, blocking_axis)
        ]
        if not extra or not extra.get("quotes"):
            return {"_result": result, "_extraction": extraction, "_candidates": candidates}

        # 代码侧防漂移：优先用阶段 2 的权威维度决策表，否则取已有 quote 的最高维度
        element_dim_map: dict[str, str] = dict(extraction.get("_element_dimensions") or {})
        if not element_dim_map:
            for q in extraction.get("quotes", []):
                elem = q.get("element_hint", "")
                dim = q.get("dimension_hint", "")
                if elem not in {"unknown", None} and dim in {"1D", "2D", "3D", "4D"}:
                    existing = element_dim_map.get(elem, "")
                    if dim > existing:
                        element_dim_map[elem] = dim

        for q in extra.get("quotes", []):
            elem = q.get("element_hint", "")
            new_dim = q.get("dimension_hint", "")
            if elem in element_dim_map and new_dim in {"1D", "2D", "3D", "4D"}:
                locked_dim = element_dim_map[elem]
                if new_dim != locked_dim:
                    q["_drift_suppressed"] = new_dim
                    q["dimension_hint"] = locked_dim

        # 合并 quotes，按 (quote前30字, element_hint) 去重
        existing_keys = {
            (q.get("quote", "")[:30], q.get("element_hint", "")): True
            for q in extraction.get("quotes", [])
        }
        new_quotes = [
            q for q in extra["quotes"]
            if (q.get("quote", "")[:30], q.get("element_hint", "")) not in existing_keys
        ]
        if not new_quotes:
            return {"_result": result, "_extraction": extraction, "_candidates": candidates}

        merged_extraction = dict(extraction)
        merged_extraction["quotes"] = extraction.get("quotes", []) + new_quotes
        merged_extraction["conflicts"] = self._dedupe_dicts(
            extraction.get("conflicts", []) + extra.get("conflicts", []), key="topic"
        )
        merged_extraction["insufficiency"] = list(set(
            extraction.get("insufficiency", []) + extra.get("insufficiency", [])
        ))[:5]

        new_candidates = self._score_candidates(merged_extraction)
        new_result = self._build_result(case_id, new_candidates, merged_extraction, prepared)
        new_result["refinement"] = {
            "stage": "L1",
            "axis": blocking_axis.get("axis", ""),
            "axis_description": blocking_axis.get("axis_description", ""),
            "competing_types": blocking_axis.get("competing_types", []),
            "added_quotes": len(new_quotes),
        }
        return {"_result": new_result, "_extraction": merged_extraction, "_candidates": new_candidates}

    def _directed_reextract(
        self,
        prepared: dict[str, Any],
        blocking_axis: dict[str, Any],
        existing_extraction: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """L1 定向重提取的薄包装（build + LLM call）。保留供单测和回归使用。"""
        req = self._build_l1_request(prepared, blocking_axis, existing_extraction)
        if not req:
            return None
        result = self.llm.chat_json(req[0], req[1])
        if not self._is_valid_extraction(result):
            return None
        result = self._normalize_extraction(result)
        result["_source"] = "llm_directed"
        return result

    def _try_directed_reextract(
        self,
        result: dict[str, Any],
        extraction: dict[str, Any],
        candidates: list[dict[str, Any]],
        prepared: dict[str, Any],
        case_id: str,
        blocking_axis: dict[str, Any],
    ) -> dict[str, Any]:
        """L1 定向重提取的薄包装（build + LLM call + apply）。保留供单测和回归使用。"""
        extra = self._directed_reextract(prepared, blocking_axis, existing_extraction=extraction)
        return self._apply_directed_reextract(result, extraction, candidates, prepared, case_id, blocking_axis, extra)

    def _dedupe_dicts(self, items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        """按指定 key 去重 dict 列表。"""
        seen: set[str] = set()
        result = []
        for item in items:
            k = str(item.get(key, ""))
            if k not in seen:
                seen.add(k)
                result.append(item)
        return result

    def _laning_tiebreak(
        self,
        candidates: list[dict[str, Any]],
        laning_signals: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        赖宁二分法象限缩圈：只在 Top-2 分差 < margin 且有 laning_signals 时调用。
        对每个赖宁维度计算 Top-2 候选各自属于哪侧，结合信号 lean/confidence 打分，
        返回得分更高的候选（或 None 表示无法决断）。
        """
        if len(candidates) < 2:
            return None
        top, second = candidates[0], candidates[1]
        top_type, second_type = top["type"], second["type"]

        scores: dict[str, float] = {top_type: 0.0, second_type: 0.0}
        used: list[str] = []

        for dim, signal in laning_signals.items():
            if not isinstance(signal, dict):
                continue
            lean_val = signal.get("lean", "unknown")
            conf = float(signal.get("confidence") or 0.0)
            if lean_val == "unknown" or conf <= 0:
                continue
            group = LANING_QUADRA.get(lean_val)
            if group is None:
                continue
            for t in (top_type, second_type):
                if t in group:
                    scores[t] += conf
                else:
                    scores[t] -= conf * 0.5
            used.append(f"{dim}→{lean_val}({conf:.2f})")

        if not used:
            return None

        if scores[top_type] == scores[second_type]:
            return None

        winner_type = top_type if scores[top_type] > scores[second_type] else second_type
        winner = top if winner_type == top_type else second
        return {
            "winner": winner,
            "scores": {t: round(s, 3) for t, s in scores.items()},
            "used_signals": used,
        }

    def _build_l2_request(
        self,
        prepared: dict[str, Any],
        top_candidates: list[dict[str, Any]],
        extraction: dict[str, Any],
    ) -> tuple[str, str] | None:
        """构造 L2 综合仲裁的 (system_prompt, user_prompt)。"""
        prompt_path = BASE_DIR / "prompts" / "synthesis_pass.md"
        if not prompt_path.exists():
            return None
        system_prompt = prompt_path.read_text(encoding="utf-8")

        full_text = prepared.get("analysis_text", "")
        if prepared.get("mode") == "qa_answers_only":
            text_label = "问卷回答"
        else:
            text_label = "用户文本"

        # 构建候选类型摘要
        candidate_blocks = []
        for cand in top_candidates[:3]:
            t = cand["type"]
            meta = self.model_a.get(t, {})
            model_a_str = "、".join(meta.get("model_a", []))
            matches = cand.get("rule_matches", [])[:3]
            conflicts = cand.get("rule_conflicts", [])[:3]
            global_conflicts = cand.get("global_conflicts", [])[:2]
            block = (
                f"候选 {t}（{meta.get('alias', '')}，{meta.get('quadra', '')}象限）"
                f"Model A: {model_a_str} | "
                f"算法分: {cand['score']:.3f}，4D证据: {cand.get('first_4d_support', 0):.3f}，3D证据: {cand.get('second_3d_support', 0):.3f} | "
                f"匹配: {'; '.join(matches) or '无'} | 冲突: {'; '.join(conflicts + global_conflicts) or '无'}"
            )
            candidate_blocks.append(block)

        # 已提取证据摘要：按 IND 命中、元素已知、维度已知、置信度 排序，取前 12 条
        quotes_with_priority = sorted(
            extraction.get("quotes", []),
            key=lambda q: (
                1 if q.get("indicator", "").startswith("IND") else 0,
                1 if q.get("element_hint") not in {"unknown", None} else 0,
                1 if q.get("dimension_hint") not in {"unknown", None} else 0,
                float(q.get("confidence") or 0),
            ),
            reverse=True,
        )[:12]
        quotes_summary = "\n".join(
            f"- {q.get('quote', '')}（{q.get('element_hint')}/{q.get('dimension_hint')}）"
            for q in quotes_with_priority
        )

        user_prompt = (
            f"【{text_label}（全文）】\n{full_text}\n\n"
            f"【已提取的关键证据】\n{quotes_summary or '无'}\n\n"
            f"【算法候选类型】\n" + "\n".join(candidate_blocks) +
            "\n\n请从整体上判断这段文字最符合哪个类型，输出 JSON。"
        )
        return system_prompt, user_prompt

    def _parse_l2_response(self, llm_raw: dict[str, Any] | None) -> dict[str, Any] | None:
        """解析 L2 综合仲裁的 LLM 返回结果。"""
        if not isinstance(llm_raw, dict) or "verdict_type" not in llm_raw:
            return None
        if llm_raw["verdict_type"] not in self.model_a:
            return None
        llm_raw["coherence_confidence"] = self._bounded_float(llm_raw.get("coherence_confidence"), 0.0)
        return llm_raw

    def _synthesis_pass(
        self,
        prepared: dict[str, Any],
        top_candidates: list[dict[str, Any]],
        extraction: dict[str, Any],
    ) -> dict[str, Any] | None:
        """L2 综合仲裁的薄包装（build + LLM call + parse）。保留供单测和回归使用。"""
        req = self._build_l2_request(prepared, top_candidates, extraction)
        if not req:
            return None
        result = self.llm.chat_json(req[0], req[1])
        return self._parse_l2_response(result)

    def _arbitrate(
        self,
        result: dict[str, Any],
        candidates: list[dict[str, Any]],
        synthesis: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        三方仲裁：算法 top、赖宁决断（若有）、综合层（若有）。
        直接修改 result 的 status/type/alias/quadra，并写入 synthesis_pass 和 arbitration 字段。
        """
        if synthesis is None:
            result["synthesis_pass"] = None
            result["arbitration"] = None
            return result

        result["synthesis_pass"] = synthesis
        verdict = synthesis.get("verdict_type")
        coherence_conf = synthesis.get("coherence_confidence", 0.0)

        algo_top = candidates[0]["type"] if candidates else None
        algo_second = candidates[1]["type"] if len(candidates) > 1 else None
        algo_top3 = {c["type"] for c in candidates[:3]}
        laning_winner = result.get("laning_tiebreak", {})
        laning_type = laning_winner.get("winner", {}).get("type") if isinstance(laning_winner, dict) else None

        voters = {
            "algorithm": algo_top,
            "laning": laning_type,
            "synthesis": verdict,
        }
        decision = "uncertain"
        reason = ""

        if coherence_conf >= 0.75:
            if verdict == algo_top:
                decision = "certain"
                reason = f"综合层高置信度（{coherence_conf:.2f}）背书算法 top {verdict}。"
            elif verdict == algo_second:
                # 综合层推翻算法排序：采纳 verdict
                decision = "certain_synthesis_override"
                reason = f"综合层高置信度（{coherence_conf:.2f}），推翻算法排序，采纳 {verdict} 而非算法 top {algo_top}。"
            elif verdict not in algo_top3:
                decision = "uncertain"
                reason = f"综合层 verdict={verdict} 不在算法 top-3 内，不采信，维持不确定。"
            else:
                decision = "certain"
                reason = f"综合层高置信度（{coherence_conf:.2f}），verdict={verdict} 在 top-3 内，采纳。"
        elif 0.5 <= coherence_conf < 0.75:
            if verdict == algo_top:
                decision = "certain"
                reason = f"综合层弱背书（{coherence_conf:.2f}）与算法一致，合并确定为 {verdict}。"
            else:
                decision = "uncertain"
                reason = f"综合层置信度 {coherence_conf:.2f} 不足且与算法分歧，维持不确定。"
        else:
            decision = "uncertain"
            reason = f"综合层置信度 {coherence_conf:.2f} 过低，不采信。"

        if "Recovered partial JSON" in str(result.get("llm_error") or "") and decision in {"certain", "certain_synthesis_override"}:
            decision = "uncertain"
            reason = "初始抽取来自截断 JSON 恢复，禁止 L2 仲裁直接确定类型。"

        result["arbitration"] = {"voters": voters, "decision": decision, "reason": reason}

        if decision in {"certain", "certain_synthesis_override"}:
            final_type = verdict  # decision ∈ {certain, certain_synthesis_override} 时 verdict 即结论
            meta = self.model_a.get(final_type, {})
            result["status"] = "certain"
            result["type"] = final_type
            result["alias"] = meta.get("alias")
            result["quadra"] = meta.get("quadra")
            result["model_a"] = meta.get("model_a", [])

            # 重排 candidates 把 verdict 提到首位，同步更新 confidence 和 explanations
            candidates_list = result.get("candidates", [])
            verdict_idx = next((i for i, c in enumerate(candidates_list) if c["type"] == verdict), None)
            if verdict_idx is not None and verdict_idx != 0:
                verdict_cand = candidates_list.pop(verdict_idx)
                candidates_list.insert(0, verdict_cand)
                result["candidates"] = candidates_list
                result["confidence"] = verdict_cand.get("score", result.get("confidence"))
                explanations = result.get("candidate_explanations", [])
                exp_idx = next((i for i, e in enumerate(explanations) if e["type"] == verdict), None)
                if exp_idx is not None and exp_idx != 0:
                    verdict_exp = explanations.pop(exp_idx)
                    explanations.insert(0, verdict_exp)
                    result["candidate_explanations"] = explanations

        return result

    def _generate_clarification(
        self,
        blocking_axis: dict[str, Any],
        candidates: list[dict[str, Any]],
        extraction: dict[str, Any],
    ) -> dict[str, Any] | None:
        """L3 打回用户：LLM 动态生成定向追问，返回 clarification_request dict。"""
        axis = blocking_axis.get("axis", "")
        axis_desc = blocking_axis.get("axis_description", axis)
        competing = blocking_axis.get("competing_types", [])
        blocking_reason = blocking_axis.get("blocking_reason", "")

        questions: list[str] = []

        # 优先尝试 LLM 动态生成
        prompt_path = BASE_DIR / "prompts" / "clarification_generator.md"
        if prompt_path.exists() and self.llm.config.enabled:
            system_prompt = prompt_path.read_text(encoding="utf-8")
            type1 = competing[0] if len(competing) > 0 else "?"
            type2 = competing[1] if len(competing) > 1 else "?"
            meta1 = self.model_a.get(type1, {})
            meta2 = self.model_a.get(type2, {})
            conflict_reasons = [
                str(c.get("reason", "")) for c in extraction.get("conflicts", [])[:3]
                if isinstance(c, dict)
            ]

            user_prompt = (
                f"竞争类型：{type1}（{meta1.get('alias', '')}）vs {type2}（{meta2.get('alias', '')}）\n"
                f"阻塞轴：{axis_desc}\n"
                f"{type1} Model A: {'、'.join(meta1.get('model_a', []))}\n"
                f"{type2} Model A: {'、'.join(meta2.get('model_a', []))}\n"
                f"已知证据冲突：{'; '.join(conflict_reasons) or '无'}\n"
                f"阻塞原因：{blocking_reason}\n\n"
                f"请生成 2-3 个能区分这两个竞争类型的定向追问，输出 JSON：{{\"questions\": [\"...\", \"...\", \"...\"]}}"
            )

            llm_result = self.llm.chat_json(system_prompt, user_prompt)
            if isinstance(llm_result, dict) and isinstance(llm_result.get("questions"), list):
                questions = [str(q) for q in llm_result["questions"][:3] if q and str(q).strip()]

        # 失败时用轴描述拼通用问题
        if not questions:
            questions = [
                f"关于以下方面，能描述一个具体的场景或感受吗？{axis_desc[:50]}",
            ]

        return {
            "axis": axis,
            "axis_description": axis_desc,
            "competing_types": competing,
            "questions": questions,
            "blocking_reason": blocking_reason,
        }

    def _refine(
        self,
        result: dict[str, Any],
        extraction: dict[str, Any],
        candidates: list[dict[str, Any]],
        prepared: dict[str, Any],
        case_id: str,
    ) -> dict[str, Any]:
        """
        三级审理编排（L1+L2 并发 → L3）。
        只在 status==uncertain 且 LLM 可用时运行。
        返回可能已升为 certain 或 clarifying 的 result。
        """
        if result["status"] != "uncertain":
            return result
        if not self.llm.config.enabled:
            return result
        typed_evidence_count = sum(
            1 for q in extraction.get("quotes", [])
            if q.get("element_hint") not in {"unknown", None}
            and q.get("dimension_hint") not in {"unknown", None}
        )
        if extraction.get("_schema_invalid") or typed_evidence_count < self.options.min_evidence:
            result["refinement"] = {
                "stage": "blocked",
                "reason": "结构化证据不足，跳过 L1/L2 以避免 unknown 或漂移证据污染评分。",
                "typed_evidence_count": typed_evidence_count,
            }
            result["report"] = self._render_report(result)
            return result

        blocking = self._identify_blocking_axis(candidates, result.get("uncertainty_reasons", []), extraction)

        # 并行准备：L1 prompt 和 L2 prompt
        l1_request = self._build_l1_request(prepared, blocking, extraction) if blocking else None
        l2_request = self._build_l2_request(prepared, candidates[:3], extraction)

        requests_list = [r for r in [l1_request, l2_request] if r is not None]
        results_list = self.llm.chat_json_parallel(requests_list)

        # 按位置解包（顺序与 requests_list 一致）
        l1_raw, l2_raw = None, None
        idx = 0
        if l1_request is not None:
            l1_raw = results_list[idx]
            idx += 1
        if l2_request is not None:
            l2_raw = results_list[idx]
            idx += 1

        # 先处理 L1：若 L1 拿到新证据且能升 certain，优先使用
        if l1_raw and blocking:
            l1_out = self._apply_directed_reextract(result, extraction, candidates, prepared, case_id, blocking, l1_raw)
            l1_result = l1_out["_result"]
            if l1_result["status"] == "certain":
                return l1_result  # 报告由 analyze() 统一渲染
            result = l1_result
            extraction = l1_out["_extraction"]
            candidates = l1_out["_candidates"]

        # 再处理 L2（用 L1 后的可能更新过的 candidates）
        if l2_raw:
            synthesis = self._parse_l2_response(l2_raw)
            result = self._arbitrate(result, candidates, synthesis)
            if result["status"] == "certain":
                return result  # 报告由 analyze() 统一渲染

        # L3：打回用户
        if blocking:
            clar = self._generate_clarification(blocking, candidates, extraction)
            if clar:
                result["status"] = "clarifying"
                result["clarification_request"] = clar

        result["report"] = self._render_report(result)
        return result

    def _follow_up_questions(self, result: dict[str, Any]) -> list[str]:
        candidates = result.get("candidates", [])
        if len(candidates) < 2:
            return []
        top_types = {item["type"] for item in candidates[:2]}
        questions = []
        if top_types & {"ILE", "LII", "SEE", "ESI", "IEE", "EII", "SLE", "LSI"}:
            questions.append("遇到新问题时，你更常先固定对象/结构来分析，还是先观察过程、节奏和变化？")
        if top_types & {"ESE", "SEI", "EIE", "IEI", "LIE", "ILI", "LSE", "SLI"}:
            questions.append("做决定前，你更依赖已经想象过的动态结果，还是会直接进入动作中边做边校正？")
        questions.extend(
            [
                "过程 vs 结果：你更享受按步骤推演，还是更想快速得到最终答案？",
                "欢快 vs 严肃：你更偏好轻松情绪共鸣，还是客观克制、保持距离？",
                "审慎 vs 果断：行动前会反复权衡舒适度，还是倾向快速切割并推进？",
            ]
        )
        return questions[:4]

    def _evidence_report_limit(self, result: dict[str, Any]) -> int:
        preprocess = result.get("preprocess", {})
        if preprocess.get("mode") == "qa_answers_only":
            return min(30, max(6, int(preprocess.get("qa_count") or 0)))
        return 6

    def _render_report(self, result: dict[str, Any]) -> str:
        status_map = {"certain": "确定", "uncertain": "不确定", "clarifying": "待澄清", "rejected": "拒绝"}
        status_cn = status_map.get(result["status"], result["status"])
        candidates_text = "、".join(
            f"{item['type']}({item['score']:.3f})" for item in result.get("candidates", [])
        )
        if result["status"] == "certain":
            conclusion = f"{result['type']} / {result['alias']}，{result['quadra']} 象限"
            model_a_text = "，".join(result["model_a"])
        else:
            conclusion = f"竞争类型：{candidates_text or '无'}"
            model_a_text = "判型不确定，暂不输出单一 Model A。"

        evidence_lines = []
        evidence_limit = self._evidence_report_limit(result)
        for item in result.get("evidence_chain", [])[:evidence_limit]:
            extra_bits = []
            if item.get("qa_index"):
                extra_bits.append(f"Q{item.get('qa_index')}")
            if item.get("_coverage_fallback"):
                extra_bits.append("coverage")
            if item.get("strength_signal") and item.get("strength_signal") != "unknown":
                extra_bits.append(f"强弱={item.get('strength_signal')}")
            if item.get("valued_signal") and item.get("valued_signal") != "unknown":
                extra_bits.append(f"重视={item.get('valued_signal')}")
            if item.get("mental_signal") and item.get("mental_signal") != "unknown":
                extra_bits.append(f"环路={item.get('mental_signal')}")
            if item.get("evidence_type") and item.get("evidence_type") != "keyword":
                extra_bits.append(f"证据={item.get('evidence_type')}")
            extra = f"（{'; '.join(extra_bits)}）" if extra_bits else ""
            evidence_lines.append(
                f"- “{item.get('quote', '')}” -> {item.get('indicator', 'unknown')}，"
                f"{item.get('element_hint', 'unknown')} / {item.get('dimension_hint', 'unknown')}{extra}。"
            )
        if not evidence_lines:
            evidence_lines.append("- 当前文本没有提取到足够稳定的行为证据。")

        preprocess = result.get("preprocess", {})
        preprocess_line = (
            f"- 输入预处理：{preprocess.get('mode', 'unknown')}，"
            f"问答组 {preprocess.get('qa_count', 0)}，"
            f"分析文本 {preprocess.get('analysis_length', 0)} / 原文 {preprocess.get('original_length', 0)} 字。"
        )

        candidate_lines = []
        for item in result.get("candidate_explanations", []):
            matched = "；".join(item.get("matched", [])[:2]) or "暂无强匹配"
            tension = "；".join(item.get("tension", [])[:1]) or "暂无主要张力"
            conflicts = "；".join(item.get("rule_conflicts", [])[:2]) or "暂无硬冲突"
            global_matches = "；".join(item.get("global_matches", [])[:2]) or "暂无全局匹配"
            global_conflicts = "；".join(item.get("global_conflicts", [])[:2]) or "暂无全局张力"
            candidate_lines.append(
                f"- {item['type']}({item['score']:.3f})：1st={item.get('first_hypothesis')}，"
                f"2nd={item.get('second_hypothesis')}；"
                f"4D主导证据={item.get('first_4d_support', 0):.3f}，"
                f"1st主轴分={item.get('first_axis_score', 0):.3f}，"
                f"3D证据={item.get('second_3d_support', 0):.3f}，"
                f"2nd创造支持={item.get('second_creative_support', 0):.3f}，"
                f"7th忽略风险={item.get('second_ignoring_risk', 0):.3f}；"
                f"匹配：{matched}；张力：{tension}；硬冲突：{conflicts}；"
                f"全局校验={item.get('global_score', 0):.3f}，匹配：{global_matches}，张力：{global_conflicts}"
            )
        if not candidate_lines:
            candidate_lines.append("- 暂无候选解释。")

        uncertain_lines = []
        for item in result.get("uncertainty_reasons", []):
            uncertain_lines.append(f"- {item}")
        for item in result.get("insufficiency", []):
            line = f"- {item}"
            if line not in uncertain_lines:
                uncertain_lines.append(line)
        for item in result.get("conflicts", []):
            kind = item.get("conflict_kind", "dimension") if isinstance(item, dict) else "dimension"
            kind_label = "维度矛盾" if kind == "dimension" else "信号疑似误判"
            reason = item.get("reason", str(item)) if isinstance(item, dict) else str(item)
            uncertain_lines.append(f"- [{kind_label}] {reason}")
        if not uncertain_lines:
            uncertain_lines.append("- 暂无明显冲突；后续可补充压力场景、人际距离、效率处理方式。")

        # 定向追问（L3 结果优先，否则回退通用问题）
        clar = result.get("clarification_request")
        if clar and clar.get("questions"):
            follow_up_lines = [f"- {q}" for q in clar["questions"]]
            follow_up_lines.insert(0, f"- 【阻塞轴：{clar.get('axis_description', clar.get('axis', ''))}】")
        else:
            follow_up_lines = [f"- {question}" for question in self._follow_up_questions(result)]
        if not follow_up_lines:
            follow_up_lines.append("- 暂无追问建议。")

        laning_line = ""
        laning_result = result.get("laning_tiebreak")
        if laning_result:
            laning_line = (
                f"- 赖宁二分法决断：{laning_result['winner']['type']}；"
                f"信号：{'; '.join(laning_result.get('used_signals', []))}；"
                f"各类型分：{laning_result.get('scores', {})}。"
            )

        ind_sources = []
        for item in result.get("evidence_chain", [])[:6]:
            ind = item.get("indicator", "")
            if ind.startswith("IND") and ind in IND_PROFILES:
                ind_sources.append(f"{ind}→{item.get('element_hint', '?')}/{item.get('dimension_hint', '?')}")
        ind_line = f"- 命中 IND 指标：{', '.join(ind_sources)}" if ind_sources else "- 未命中具名 IND 指标（或使用关键词规则）。"

        # 精化层标注
        refinement = result.get("refinement")
        refinement_note = ""
        if refinement:
            stage = refinement.get("stage", "")
            added = refinement.get("added_quotes", 0)
            axis = refinement.get("axis", "")
            refinement_note = f"（经 {stage} 定向重提取{f'，轴={axis}' if axis else ''}，补充 {added} 条证据）"

        # 综合仲裁展示
        synthesis_lines = []
        synthesis = result.get("synthesis_pass")
        arbitration = result.get("arbitration")
        if synthesis:
            synthesis_lines.append(
                f"- 综合推理判断：{synthesis.get('verdict_type', '?')}，"
                f"置信度 {synthesis.get('coherence_confidence', 0):.2f}"
            )
            if synthesis.get("narrative"):
                synthesis_lines.append(f"  理由：{synthesis['narrative']}")
            if synthesis.get("why_not_competitor"):
                synthesis_lines.append(f"  排除 {synthesis.get('main_competitor', '?')}：{synthesis['why_not_competitor']}")
        if arbitration:
            synthesis_lines.append(
                f"- 三方仲裁决策：{arbitration.get('decision', '?')}，原因：{arbitration.get('reason', '')}"
            )

        sections = [
            f"1. **判型状态**：{status_cn}{refinement_note}",
            f"2. **类型结论**：{conclusion}",
            "3. **输入预处理**：",
            preprocess_line,
            "4. **核心证据链**：",
            *evidence_lines,
            "5. **候选解释**：",
            *candidate_lines,
            "6. **七大二分法核对**：",
            "- 已纳入接受/生产、接触/惰性、引导/分离、静态/动态类型、理性/非理性整模型校验；结果体现在候选解释的全局校验项。",
            ind_line,
        ]
        if laning_line:
            sections.append(laning_line)
        if synthesis_lines:
            sections.append("6.5. **综合推理层**：")
            sections.extend(synthesis_lines)
        sections += [
            f"7. **完整 Model A 架构图**：{model_a_text}",
            "8. **不确定点与建议追问**：",
            *uncertain_lines,
            "9. **下一轮追问建议**：",
            *follow_up_lines,
        ]
        return "\n".join(sections)

    def _write_artifacts(self, case_id: str, result: dict[str, Any]) -> None:
        safe_case_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", case_id)
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        (OUTPUT_DIR / f"{safe_case_id}.json").write_text(payload, encoding="utf-8")
        (LOG_DIR / "kernel1.log").open("a", encoding="utf-8").write(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "case_id": case_id,
                    "status": result.get("status"),
                    "type": result.get("type"),
                    "confidence": result.get("confidence"),
                    "input_encoding": result.get("input_encoding", "utf-8"),
                    "extraction_source": result.get("extraction_source"),
                    "llm_error": result.get("llm_error"),
                    "llm_raw_path": result.get("llm_raw_path"),
                    "llm_request": result.get("llm_request"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
