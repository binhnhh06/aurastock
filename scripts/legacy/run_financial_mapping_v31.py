"""Read only audit reports and produce traceable candidate mapping; no scoring."""
import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)

import argparse
from pathlib import Path
from core.financial_mapping_v31 import compile_financial_review

ROOT = Path(__file__).resolve().parents[2]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-dir", type=Path, default=ROOT / "data/fundamentals/audit")
    parser.add_argument("--out", type=Path, default=ROOT / "data/fundamentals/mapping_review")
    args = parser.parse_args()
    s = compile_financial_review(args.audit_dir, args.out)
    print("=== BATDAYSTOX SSI - FINANCIAL MAPPING REVIEW V3.1 ===")
    for k in ("companies", "years", "exact_candidate_metrics", "blocked_critical", "provisional_roes", "ready_for_score"):
        print(f"{k}: {s[k]}")
    print("FINISHED: all values are candidate-only. No Smart Rating scores were created.")
    for key,p in s["outputs"].items():
        print(f"{key}: {p}")

if __name__ == "__main__":
    main()
