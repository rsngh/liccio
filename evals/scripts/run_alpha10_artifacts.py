"""Alpha 10 evidence bundle (WS20).

Generates the scale/production-lab artifacts: the large empirical corpus, the v2
storage/perf scaling sweep, and the expanded security/prompt-injection benchmark.
"""

from __future__ import annotations

import json
from pathlib import Path

REPORTS = Path("evals/reports")


def main() -> int:
    from acp.evaluation.large_corpus import generate_large_corpus
    from acp.evaluation.scale_benchmark_v2 import run_scale_benchmark_v2
    from acp.evaluation.security_benchmark_v2 import run_security_benchmark_v2

    REPORTS.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "large_empirical_corpus.json": generate_large_corpus(),
        "storage_scale_v2.json": run_scale_benchmark_v2(sizes=[50, 100, 200]),
        "security_injection_v2.json": run_security_benchmark_v2(),
    }
    for name, data in artifacts.items():
        (REPORTS / name).write_text(json.dumps(data, indent=2, default=str) + "\n")
        print(f"wrote {REPORTS / name}")
    corpus = artifacts["large_empirical_corpus.json"]
    print(f"corpus: n_sufficient={corpus.get('n_sufficient')} "
          f"pairs={corpus.get('n_preference_pairs')}")
    sec = artifacts["security_injection_v2.json"]["summary"]
    print(f"security v2: handled={sec.get('all_handled')} leak={sec.get('any_secret_leak')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
