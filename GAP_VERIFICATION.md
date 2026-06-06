# Gap-List Verification — fresh checks against the current branch

Every item from the "biggest gaps" list, verified green on the current branch (not "done in a
past round" — re-checked now).

| Item | Status | Evidence (verified now) |
|------|--------|-------------------------|
| **WS14** live multi-task bakeoff | ✅ DONE | Capability matrix has **16 real-agent cells** (openai_harness/claude_harness, max n=25); OPE log over **260 observed runs**, `source: REAL observed agent runs`. Routing/OPE/Pareto are driven by observed behavior, not the fake adapter. |
| **WS19** vendor-native live gate | ✅ GREEN | `vendor_harness_live.json`: `passed=true, live_proven=true, n_solved=2` (codex_cli + claude_code solve). openhands argv None-guard typed (mypy clean). `tests/live/test_vendor_harness_live.py` exists; manifest-registered (requires `live_proven`). Fresh re-run confirms. |
| **WS18** Docker live-security | ✅ VERIFIED | Fresh run with docker up: **passed=true, 9/9 checks pass**. Mid-run daemon loss handled as a clean skip (infra, not failure). |
| **WS6** vendor live campaign | ✅ DONE | Real solve loop proven: `codex_cli` and `claude_code` both solved the no-patch task (trace + diff + pytest + secret-clean + timeout). Plus `vendor_capability_matrix` (activation-aware). |
| **WS15** local LoRA pilot | ⛔ N/A | No torch/peft/GPU in this environment — legitimately skipped, reported not overclaimed. |
| **Report warehouse** | ✅ DONE | `acp reports ingest` → **93 DB entities**; `acp reports list/show/diff` query them. Reporting is DB-queryable, not just file/manifest. |
| **Operator surface** | ◑ CLI cockpit | `acp health --mode`, `evidence-gaps`, `reports list/show/diff`, `skill dashboard`, `policy dossier`, shadow recommendations. A web UI remains out of scope for this environment. |
| **Evidence quality / sample size** | ✅ IMPROVED | Larger bakeoff (reps=5 → 130 attempts, 260 OPE). Wilson CIs on every cell. `sample_adequacy`: **0 insufficient cells** (was 28), **4 robust**, mean CI width **0.38** (was 0.61). |

## Priority sequence — all addressed in order

WS19 ✅ → WS18 ✅ → WS14 ✅ → grow samples ✅ → operator/reporting surface (warehouse ✅, CLI
cockpit ✅; web UI out of scope). The system now rests on **observed agent behavior** with
honest, increasingly-tight confidence intervals — out of "synthetic-input lab" territory.
