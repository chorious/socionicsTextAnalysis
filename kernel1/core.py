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
        if self._is_valid_extraction(llm_result):
            llm_result = self._normalize_extraction(llm_result)
            llm_result["_source"] = "llm"
            return llm_result
        fallback = self._heuristic_extract(text)
        fallback["_source"] = "heuristic"
        fallback["_llm_error"] = self.llm.last_error
        fallback["_llm_raw_path"] = getattr(self.llm, "last_raw_path", None)
        fallback["_llm_request"] = getattr(self.llm, "last_request_meta", None)
        return fallback

    def _is_valid_extraction(self, data: Any) -> bool:
        return isinstance(data, dict) and isinstance(data.get("quotes"), list)

    def _normalize_extraction(self, data: dict[str, Any]) -> dict[str, Any]:
        allowed_elements = {"Ne", "Ni", "Se", "Si", "Te", "Ti", "Fe", "Fi", "unknown"}
        allowed_dimensions = {"1D", "2D", "3D", "4D", "unknown"}
        cleaned_quotes = []
        for item in data.get("quotes", [])[:8]:
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

        data["quotes"] = cleaned_quotes
        data["conflicts"] = data.get("conflicts", [])[:5] if isinstance(data.get("conflicts"), list) else []
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
            if len(quotes) >= 12:
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

        hard_uncertain = no_4d or no_3d or few_evidence or conflicts

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
            "confidence": top["score"],
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
            "dichotomy_signals": extraction.get("dichotomy_signals", {}),
            "laning_signals": laning_signals,
            "laning_tiebreak": laning_result,
            "conflicts": conflicts,
            "insufficiency": insufficiency,
            "uncertainty_reasons": self._uncertainty_reasons(top, second, evidence_count, conflicts, insufficiency, laning_result),
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
        if conflicts:
            reasons.append("存在未解决的证据冲突。")
        if insufficiency:
            reasons.extend(str(item) for item in insufficiency)
        return reasons

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

    def _render_report(self, result: dict[str, Any]) -> str:
        status_cn = "确定" if result["status"] == "certain" else "不确定"
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
        for item in result.get("evidence_chain", [])[:6]:
            extra_bits = []
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
            uncertain_lines.append(f"- 冲突：{item.get('reason', item)}")
        if not uncertain_lines:
            uncertain_lines.append("- 暂无明显冲突；后续可补充压力场景、人际距离、效率处理方式。")
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

        sections = [
            f"1. **判型状态**：{status_cn}",
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
