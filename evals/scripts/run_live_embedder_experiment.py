"""Alpha 6, WS8 — live OpenAI embedder retrieval experiment (uses OPENAI_API_KEY).

Runs the retrieval benchmark on the same synthetic repo with the hashing default
vs the real OpenAI embedder, and reports the recall@k / MRR delta — a practical
measure of what a real embedder buys for context retrieval. Writes a redacted
artifact to ``reports/live/alpha6_openai_embedder_experiment.json``.

Skips cleanly (exit 0) without a key.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from acp.evaluation.retrieval_benchmark import generate_synthetic_repo, run_benchmark
from acp.observability.live_report import redact_report

OUT = Path("reports/live/alpha6_openai_embedder_experiment.json")


def _bench(repo, gold, embedder_kind: str) -> dict:
    os.environ["ACP_EMBEDDER"] = embedder_kind
    from acp.core.config import reset_settings

    reset_settings()
    rep = run_benchmark(repo, gold, strategy="hybrid_keyword_embedding")
    return {"recall_at_5": rep.recall_at_5, "recall_at_10": rep.recall_at_10,
            "mrr": rep.mrr, "avg_tokens": rep.avg_tokens,
            "secret_leakage": rep.secret_leakage_count}


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("[skip] no OPENAI_API_KEY in environment")
        return 0
    os.environ.setdefault("ACP_OPENAI_API_KEY", os.environ["OPENAI_API_KEY"])

    # Confirm the OpenAI embedder is actually available before paying for it.
    os.environ["ACP_EMBEDDER"] = "openai"
    from acp.context.embeddings import OpenAIEmbedder
    from acp.core.config import reset_settings

    reset_settings()
    if not OpenAIEmbedder().available:
        print("[skip] openai embedder unavailable (SDK/key)")
        return 0

    tmp = Path(tempfile.mkdtemp())
    repo = tmp / "synthetic"
    gold = generate_synthetic_repo(repo, n_files=40, seed=7)

    hashing = _bench(repo, gold, "hashing")
    openai = _bench(repo, gold, "openai")
    os.environ.pop("ACP_EMBEDDER", None)

    report = {
        "experiment": "alpha6_live_openai_embedder_retrieval",
        "n_tasks": len(gold),
        "embedders": {"hashing": hashing, "openai": openai},
        "delta": {
            "recall_at_5": round(openai["recall_at_5"] - hashing["recall_at_5"], 4),
            "recall_at_10": round(openai["recall_at_10"] - hashing["recall_at_10"], 4),
            "mrr": round(openai["mrr"] - hashing["mrr"], 4),
        },
    }
    safe = redact_report(report)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(safe, indent=2) + "\n")
    print(f"hashing recall@10={hashing['recall_at_10']:.3f} mrr={hashing['mrr']:.3f}")
    print(f"openai  recall@10={openai['recall_at_10']:.3f} mrr={openai['mrr']:.3f}")
    print(f"delta recall@10={report['delta']['recall_at_10']:+.3f} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
