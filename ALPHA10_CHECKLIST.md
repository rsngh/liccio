# Alpha 10 — scale & production-lab hardening: checklist

Alpha 10 scales the lab and hardens the production path: a large empirical corpus,
a v2 scale benchmark, an expanded security/prompt-injection suite, and model/data
governance. (Docker/vendor *live* campaigns are gated to Docker/key-capable CI.)

## Workstreams delivered

| WS | Delivered |
| --- | --- |
| 11 | **Large empirical corpus** (`evaluation/large_corpus.py`): 930 sufficient capability cells, 1,740 preference pairs, Pareto frontier sizes, OPE-overlap estimate. |
| 17 | **Storage/perf benchmark v2** (`evaluation/scale_benchmark_v2.py`): 6 measured ops per N + sub-quadratic verdict. |
| 18 | **Security/prompt-injection v2** (`evaluation/security_benchmark_v2.py`): 10 attack classes incl. supply-chain mutation + data/reward poisoning — all escalated/flagged, zero secret leak. |
| 19 | **Model/data governance** (`training/governance.py`): DatasetAccessPolicy / ModelTrainingPermission / ModelRollbackPolicy + `governance_check` (no private-repo data into global datasets without allowlist). |
| 12/13/16 | Docker live-security gate, vendor-harness live campaign, local LoRA experiment — **gated** to Docker/key/GPU-capable environments (skip cleanly here). |
| 20 | This checklist + `ALPHA10_REPORT.md` + `make alpha10-artifacts`. |

## Required artifacts (committed, manifest-validated)

- `evals/reports/large_empirical_corpus.json`
- `evals/reports/storage_scale_v2.json`
- `evals/reports/security_injection_v2.json`

## Gate

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src
make alpha9-artifacts && make alpha10-artifacts && acp reports validate && acp health
```
