from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from kernel1.core import AnalyzeOptions, Kernel1Analyzer
from kernel1.llm import LLMClient, LLMConfig


BASE_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = BASE_DIR / "synthetic_samples"
RESULTS_DIR = BASE_DIR / "results"


def _load_pairs() -> list[tuple[Path, Path]]:
    pairs = []
    for txt in sorted(SAMPLES_DIR.glob("*.txt")):
        gt = txt.with_suffix(".gt.json")
        if gt.exists():
            pairs.append((txt, gt))
    return pairs


def _evaluate(result: dict, gt: dict) -> dict:
    """Return verdict + per-criterion booleans."""
    expected = gt.get("expected_signals", {})
    gt_type = gt["ground_truth"]["type"]
    top_must_include = expected.get("top_candidate_must_include", [gt_type])
    min_conf = float(expected.get("min_confidence_target", 0.80))
    must_cover = set(expected.get("evidence_must_cover_elements", []))
    should_cover = set(expected.get("evidence_should_cover_elements", []))

    candidates = result.get("candidates", []) or []
    top = candidates[0]["type"] if candidates else None
    confidence = float(result.get("confidence", 0.0) or 0.0)

    elements_in_evidence = {
        q.get("element_hint")
        for q in result.get("evidence_chain", [])
        if q.get("element_hint") not in {None, "unknown"}
    }

    top_ok = top in set(top_must_include) if top else False
    conf_ok = confidence >= min_conf
    must_ok = must_cover.issubset(elements_in_evidence)
    should_ok = should_cover.issubset(elements_in_evidence)

    return {
        "expected_type": gt_type,
        "top_candidate": top,
        "top_ok": top_ok,
        "confidence": confidence,
        "min_conf_target": min_conf,
        "conf_ok": conf_ok,
        "must_cover_elements": sorted(must_cover),
        "missing_must": sorted(must_cover - elements_in_evidence),
        "must_ok": must_ok,
        "should_cover_elements": sorted(should_cover),
        "missing_should": sorted(should_cover - elements_in_evidence),
        "should_ok": should_ok,
        "elements_in_evidence": sorted(e for e in elements_in_evidence if isinstance(e, str)),
        "pass": top_ok and conf_ok and must_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run synthetic samples eval against Kernel1.")
    parser.add_argument("--llm", action="store_true", help="Enable local LLM extraction.")
    parser.add_argument("--ref-cards", default=None, help="Override reference cards filename.")
    parser.add_argument("--save", action="store_true", help="Write a result JSON under eval/results/.")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    pairs = _load_pairs()
    if not pairs:
        print(f"no samples in {SAMPLES_DIR}")
        return 2

    options = AnalyzeOptions(ref_cards_filename=args.ref_cards) if args.ref_cards else None
    llm = LLMClient(LLMConfig(enabled=True)) if args.llm else LLMClient(LLMConfig(enabled=False))
    analyzer = Kernel1Analyzer(llm=llm, options=options)
    active_cards = analyzer._active_ref_cards_name()

    rows = []
    passes = 0
    for txt_path, gt_path in pairs:
        text = txt_path.read_text(encoding="utf-8")
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        case_id = gt.get("case_id") or txt_path.stem
        result = analyzer.analyze(text=text, case_id=f"synth-{case_id}")
        verdict = _evaluate(result, gt)
        verdict["case_id"] = case_id
        rows.append(verdict)
        if verdict["pass"]:
            passes += 1
        print(
            f"[{case_id}] expect={verdict['expected_type']:<3} top={verdict['top_candidate'] or '-':<4} "
            f"conf={verdict['confidence']:.3f} pass={'Y' if verdict['pass'] else 'N'} "
            f"miss={verdict['missing_must']}"
        )

    total = len(rows)
    print(f"\nsummary: {passes}/{total} passed (ref_cards={active_cards}, llm={args.llm})")

    if args.save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out = {
            "ts": int(time.time()),
            "ref_cards": active_cards,
            "llm_enabled": args.llm,
            "rows": rows,
            "pass_count": passes,
            "total": total,
        }
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_path = RESULTS_DIR / f"synthetic_{stamp}.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved: {out_path}")

    return 0 if passes == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
