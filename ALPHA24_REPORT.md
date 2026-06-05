# Alpha 24 — A Trusted Operating System for Coding-Agent Intelligence

Mission: turn ACP into the industry reference for measurement-trusted coding-agent
orchestration — advisor escalation, weak-model ensembles, topology learning, harness
evolution, context/memory optimization, abstention, distillation, and research-grade evals.
All 3 tiers / 15 areas delivered with real modules, unit tests, and artifacts (live where
appropriate), honoring the safety invariants: contaminated/inconclusive attempts never
train; measured gain required before deploy; poisoning blocked; staged-canary + rollback;
secret-scanned artifacts; timeouts are infra, not capability.

## Tier 1 — live orchestration

| # | Area | Result |
|---|------|--------|
| 1 | Advisor escalation | LIVE (gpt-4o-mini exec + gpt-4o advisor): capable executor solves single-shot → advisor **never called** (0 waste); a disclosed handicapped executor stalls at 0.33 → **1.0 with advisor** (+0.667, 2 calls). Advisory-only contract. |
| 2 | Weak-model best-of-k | LIVE cost curve (blind generator + held-out pytest proof): single-shot reliability already 1.0 → best-of-k adds linear cost for flat solve rate ⇒ **k=1 Pareto-optimal**. Honest measurement-trust finding. |
| 3 | Topology controller search | Offline search found a **36% cheaper** controller (cost 2.87→1.85) at equal success, safety-preserving (security never skips strict verify). |
| 4 | Meta-Harness | Patch search accepts only safe + improving + negative-transfer-bounded harness patches; eval-script/gate-weakening patches rejected; canary-gated. |
| 5 | Synthetic task generator | Two-player synthesizer→accept loop: every generated task proven (offline) buggy-fails + reference-passes + no leakage; targets sparse capability cells. |

## Tier 2 — context, memory, abstention, training data, boundaries

| # | Area | Result |
|---|------|--------|
| 6 | Context-strategy optimizer | Real free retrieval bakeoff: grep hit 1.0 == embedding hit 1.0 → optimizer picks **grep** (cheaper). Chosen by downstream/cost, not recall. |
| 7 | Memory lifecycle / aging | Governed memory: scope-isolated (no cross-tenant leak), poison-blocked (4/4), aging degrades + revision repairs (monotonic). |
| 8 | SDB contracts | propose→verify→commit|reject with typed reject reasons + partial-result policy; nothing commits without every deterministic verifier. |
| 9 | Selective abstention | Sufficient-context gate → answer/ask_for_spec/retrieve_more/consult_advisor/run_discovery/abstain; abstention recorded inconclusive, never a capability failure. |
| 10 | Workflow distillation | Repo-disjoint holdout datasets (context_selector/repair/viability) with memorization audit (0 overlap) + majority-class smoke; secret-clean. |

## Tier 3 — research frontier

| # | Area | Result |
|---|------|--------|
| 11 | HeavySkill | LIVE: easy tasks single-shot (no waste); medium/hard engage + solve with self-consistency pruning cutting verification **40–80%**. |
| 12 | Tool-use RL data | Tool-N1 binary rewards (format + functional), malformed-rate audit, HAR/HFR summary, secret-clean JSONL export. |
| 13 | DGM variant archive | Governed quality-diversity archive (score+novelty); un-sandboxed / gate-weakening / prod-mutating variants rejected; high-risk → human review; archive ≠ deploy. |
| 14 | DeepConf pruning | Prune low-confidence candidates before expensive verification; confidence-weighted vote; early-stop; high-risk conservative floor. |
| 15 | Research benchmark | Algorithmic-vs-tuning classifier; tuning-only reward capped; research tasks route to advisor+HeavySkill+topology search (≠ bugfix). |

## North-star

ACP now answers, with evidence: should this task run; which model/harness; consult an
advisor; which context strategy; which topology; which skill; sample many cheap candidates;
abstain or ask for a spec; can we trust the measurement; can this policy/skill/harness be
promoted; what to learn next. The recurring honest finding across live experiments — strong
models are at ceiling on easy tasks, so extra compute (best-of-k, advisor) is correctly
**withheld** and only engaged where it measurably helps (handicapped executor, hard tiers) —
is the system working as designed: it spends compute only where evidence justifies it.

## Gate

```
uv run pytest -q --timeout=300
uv run ruff check . && uv run mypy src
uv run alembic upgrade head
uv run acp reports validate    # 84 artifacts valid
```
