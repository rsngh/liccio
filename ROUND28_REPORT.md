# Round 28 — Alpha 31–41: Achieved vs Not-Done Delta

Per the directive: do/test everything feasible; report the delta honestly.

## Achieved (built + tested this round)

| Sprint | Deliverable | Status |
|--------|-------------|--------|
| Test infra | **pytest-xdist `-n 2`** gate (~5:44 vs ~9:44 serial, ~40% faster; `-n 4` oversubscribes the pytest-in-pytest tests) | ✅ adopted |
| Alpha 32 | **Guarded PR pipeline** — verified draft → `acp/draft-*` feature branch, PR description, rollback plan, **zero protected-branch writes** (live-proven 3/5); ReviewerAssignmentPolicy | ✅ + live |
| Alpha 34 | **Operator inbox** `acp shadow inbox/show/label`; human override → training data | ✅ |
| Alpha 36 | **Deployment governance** — RBAC (viewer/operator/admin), AuditLog (every write-capable action), tenant isolation | ✅ |
| Alpha 37 | **Kubernetes sandbox** — manifests + static validation AND a **LIVE gauntlet 8/8 on a real kind cluster** (root rejected, OOM kill, RO root, no SA token, quota/netpol applied, cleanup) | ✅ + LIVE 8/8 |
| Alpha 38 | **Compute policy v2** — 8 arms; variance→best_of_k vs systematic→advisor/frontier; MarginalValueReport | ✅ |
| Alpha 39 | **Skill economy v3** — SkillMarket (compete per scope, cost-adjusted lift, robust + activation-aware), SkillValueLedger | ✅ |
| Alpha 40 | **Harness-benefit loop** — HAR/HFR/PWL report, activation + adherence datasets, adherence-decay benchmark | ✅ |
| Alpha 31 | **Repo-replay components** — KnownFixVerifier, hidden-test verifier, PatchEquivalenceJudge, PostMergeReplay | ✅ |
| Alpha 41 | **Policy-graph warehouse** — serialize/deserialize, repo_family signature, explorer, cross-repo warm-start | ✅ |

New tests this round: compute_policy_v2 (8), skill_market (5), harness_benefit (4),
repo_replay_components (6), kubernetes_sandbox (5), deployment_governance (6),
policy_graph_warehouse (4), guarded_pr (+1 reviewer) — all under xdist.

*Live k8s: the user installed `kind`; a real cluster (k8s v1.30.4, worked around the host's
cgroup-v1 via an older node image) ran the sandbox gauntlet against real pods.

## Not done (honest delta) — and why

- **Alpha 33 vendor corpus at 1000+ cells**: NOT reached at scale. Codex/Claude CLIs are
  intermittently degraded in this env (the activation-aware self-catch is exactly why we
  don't trust degraded runs); a 1000-cell campaign needs reliable vendor CLIs + multiple
  repos. Vendor proof remains at the live-gate + activation-aware-matrix tier.
- **Alpha 31 real GitHub issue ingestion**: env-blocked (no network/auth). Built the ingestor
  CONTRACT (GitHubIssueIngestor) + the offline verification components; real-history ingest
  is the remaining piece.
- **NetworkPolicy ENFORCEMENT (Alpha 35/37)**: kind's default kindnet does not enforce
  NetworkPolicy, so the policy is applied + validated but egress isn't blocked live (would
  need a calico CNI). Recorded honestly in the artifact.
- **Alpha 36 live Postgres/object-store/worker-queue deploy**: the SQLAlchemy layer already
  supports a Postgres DSN and the RBAC/audit/tenant models are built, but a live multi-node
  Postgres + object-store + remote-worker deployment is not stood up here.
- **LoRA**: N/A (no GPU) — correctly deferred.
- **Operator WEB UI**: backend/CLI surfaces built; a web UI is out of scope for this env.

## Net

The delta is small and concentrated in **scale + live-infra** items that need network, a
policy-enforcing CNI, or a multi-node deployment — not missing logic. Every Alpha 31–41
sprint has its core built and tested; the k8s sandbox is even live-proven on a real cluster.
