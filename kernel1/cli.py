from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import Kernel1Analyzer


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Run Kernel1 Socionics MVP analysis.")
    parser.add_argument("--text-file", type=Path, required=True, help="UTF-8 text file to analyze.")
    parser.add_argument("--case-id", default=None, help="Optional case id.")
    parser.add_argument("--report-only", action="store_true", help="Print only the Markdown report.")
    args = parser.parse_args()

    text = args.text_file.read_text(encoding="utf-8")
    result = Kernel1Analyzer().analyze(text=text, case_id=args.case_id)
    if args.report_only:
        print(result["report"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
