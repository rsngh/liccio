"""DGM-style open-ended variant archive (Alpha 24 area 13).

The Darwin Gödel Machine modifies its own codebase and keeps an ARCHIVE of successful agent
variants, selecting parents to explore from. ACP adopts the archive idea — quality-diversity
exploration over harness/agent variants — WITHOUT uncontrolled self-modification. Every
variant passes hard governance gates before it can enter the archive, and entering the
archive is not deployment: a found improvement is still staged-canary gated elsewhere.

Hard gates (a variant violating any is rejected, never archived):
- must declare a sandbox (no un-sandboxed evaluation);
- must NOT weaken measurement/verification (no disabling secret scan or verification);
- must NOT target production mutation directly;
- high-risk variants require a human-review flag before promotion (recorded, not auto).
"""

from __future__ import annotations

from dataclasses import dataclass, field

UNSAFE_KEYS = ("disable_secret_scan", "skip_verification", "weaken_gate",
               "mutate_production", "bypass_canary")


@dataclass
class Variant:
    id: str
    params: dict
    parent_id: str | None = None
    generation: int = 0
    score: float = 0.0
    novelty: float = 0.0
    accepted: bool = False
    reject_reason: str | None = None
    requires_human_review: bool = False


def safety_check(variant: Variant) -> tuple[bool, str]:
    """Reject variants that would bypass governance. Returns (safe, reason)."""
    for k in UNSAFE_KEYS:
        if variant.params.get(k):
            return False, f"unsafe: {k}"
    if not variant.params.get("sandbox", False):
        return False, "no sandbox declared"
    return True, "safe"


def novelty_score(variant: Variant, archive: list) -> float:
    """Behavioural novelty: mean param-vector distance from archived variants (0..1-ish)."""
    if not archive:
        return 1.0
    keys = sorted(k for k in variant.params if isinstance(variant.params[k], (int, float))
                  and k not in UNSAFE_KEYS)
    if not keys:
        return 0.0
    def vec(p):
        return [float(p.params.get(k, 0)) for k in keys]
    v = vec(variant)
    dists = []
    for other in archive:
        ov = vec(other)
        dists.append(sum(abs(a - b) for a, b in zip(v, ov, strict=False)) / len(keys))
    return round(sum(dists) / len(dists), 4)


@dataclass
class VariantArchive:
    variants: list = field(default_factory=list)
    rejected: list = field(default_factory=list)

    def add(self, variant: Variant) -> bool:
        safe, reason = safety_check(variant)
        if not safe:
            variant.accepted = False
            variant.reject_reason = reason
            self.rejected.append(variant)
            return False
        variant.novelty = novelty_score(variant, self.variants)
        if variant.params.get("risk") == "high":
            variant.requires_human_review = True
        variant.accepted = True
        self.variants.append(variant)
        return True

    def best(self) -> Variant | None:
        return max(self.variants, key=lambda v: v.score) if self.variants else None

    def select_parents(self, k: int = 2) -> list:
        """Quality-diversity parent selection: blend score and novelty."""
        ranked = sorted(self.variants, key=lambda v: (v.score + v.novelty), reverse=True)
        return ranked[:k]


def evolve(seed_params: dict, *, propose_fn, eval_fn, generations: int = 3,
           children_per_gen: int = 3) -> VariantArchive:
    """Run governed quality-diversity evolution; only safe variants enter the archive.

    ``propose_fn(parent_params, child_index) -> dict`` mutates params; ``eval_fn(params) ->
    float`` scores a variant offline. Parents are selected by score+novelty each generation.
    """
    archive = VariantArchive()
    root = Variant(id="v0", params=seed_params, generation=0, score=eval_fn(seed_params))
    archive.add(root)
    counter = 1
    for gen in range(1, generations + 1):
        parents = archive.select_parents(k=2) or [root]
        for parent in parents:
            for c in range(children_per_gen):
                params = propose_fn(parent.params, c)
                v = Variant(id=f"v{counter}", params=params, parent_id=parent.id,
                            generation=gen, score=eval_fn(params))
                archive.add(v)
                counter += 1
    return archive
