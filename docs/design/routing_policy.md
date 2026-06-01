# Routing policy

`RoutingPolicy` protocol → `choose_action` returns a `PolicyDecision` that always
carries `action_probability` (propensity), `context_key`, exploration mode/reason,
and seed. Implementations: `HeuristicRouter` (risk-based v1) and
`SimulatedBanditPolicy` (epsilon-greedy / Thompson over per-context arms).
Hard constraints (`apply_constraints`) filter unavailable agents, clamp cost/
parallelism, and force human review for high-risk/experimental policies.
Off-policy evaluation (IPS/SNIPS) rejects logs missing valid propensities.
`PolicyRegistry` supports champion/challenger/canary and rollback.
