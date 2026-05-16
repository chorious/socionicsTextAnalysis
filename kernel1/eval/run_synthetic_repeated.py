"""v0.10 stability check: 同一份输入连跑 N 次,断言 verdict 一致率。

用法:
    python -m kernel1.eval.run_synthetic_repeated --input path/to/text.txt --runs 3
    python -m kernel1.eval.run_synthetic_repeated --sample ile_alpha_001 --runs 3

通过 --no-llm 强制走 heuristic(用于本地验证脚本路径连通)。默认走 LLM,
对接 192.168.50.20:8101 的 qwen3.6-27b-nvfp4。

验收标准:
    - verdict 一致率 ≥ 2/3 (即 N 次中有 ⌈N*2/3⌉ 次 verdict 相同),或
    - N 次全部 uncertain (type==None)
跳变 case(出现 ILE certain + null clarifying 等混合)直接判失败。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from kernel1.core import AnalyzeOptions, Kernel1Analyzer
from kernel1.llm import LLMClient, LLMConfig


BASE_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = BASE_DIR / "synthetic_samples"


def _load_input(args: argparse.Namespace) -> tuple[str, str]:
    if args.input:
        path = Path(args.input)
        return path.stem, path.read_text(encoding="utf-8")
    if args.sample:
        path = SAMPLES_DIR / f"{args.sample}.txt"
        return args.sample, path.read_text(encoding="utf-8")
    raise SystemExit("必须指定 --input 或 --sample")


def _build_analyzer(no_llm: bool, ref_cards: str | None) -> Kernel1Analyzer:
    if no_llm:
        client = LLMClient(LLMConfig(enabled=False))
    else:
        # 接本地 vLLM(qwen3.6-27b-nvfp4)
        endpoint = os.environ.get("KERNEL1_LLM_ENDPOINT", "http://192.168.50.20:8101/v1/chat/completions")
        model = os.environ.get("KERNEL1_LLM_MODEL", "qwen3.6-27b-nvfp4")
        client = LLMClient(LLMConfig(
            enabled=True,
            endpoint=endpoint,
            model=model,
        ))
    options = AnalyzeOptions(ref_cards_filename=ref_cards) if ref_cards else AnalyzeOptions()
    return Kernel1Analyzer(llm=client, options=options)


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.10 stability check")
    parser.add_argument("--input", help="文本文件路径(优先)")
    parser.add_argument("--sample", help="synthetic_samples 下的 sample id(如 ile_alpha_001)")
    parser.add_argument("--runs", type=int, default=3, help="重跑次数(默认 3)")
    parser.add_argument("--ref-cards", default=None, help="reference_cards 文件名")
    parser.add_argument("--no-llm", action="store_true", help="走 heuristic 不调 LLM")
    args = parser.parse_args()

    case_id, text = _load_input(args)
    print(f"[input] case_id={case_id} 长度={len(text)} runs={args.runs} no_llm={args.no_llm}")
    print()

    verdicts: list[tuple[str | None, str, float]] = []
    for i in range(args.runs):
        analyzer = _build_analyzer(args.no_llm, args.ref_cards)
        result = analyzer.analyze(text, case_id=f"{case_id}-run{i + 1}")
        verdict = result.get("type")
        status = result.get("status", "?")
        confidence = float(result.get("confidence", 0.0) or 0.0)
        verdicts.append((verdict, status, confidence))
        print(f"  run {i + 1}: type={verdict!s:>5}  status={status:>11}  conf={confidence:.3f}")

    # 一致性分析
    types_only = [v for v, _, _ in verdicts]
    counter = Counter(types_only)
    top_type, top_count = counter.most_common(1)[0]
    threshold = (args.runs * 2 + 2) // 3  # ⌈runs*2/3⌉
    all_uncertain = all(v is None for v in types_only)
    consistent = top_type is not None and top_count >= threshold
    mixed = (not consistent) and (not all_uncertain)

    print()
    print(f"[summary] verdict 分布: {dict(counter)}")
    if consistent:
        print(f"[result] ✓ 一致 ({top_count}/{args.runs} 为 {top_type})")
        return 0
    if all_uncertain:
        print(f"[result] ✓ 全部 uncertain (no flip-flop)")
        return 0
    print(f"[result] ✗ 跳变 — verdict 不一致且非全 uncertain")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
