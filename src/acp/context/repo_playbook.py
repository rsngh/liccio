# ruff: noqa: E501
"""Self-evolving repo playbook (Agentic Context Engineering 2510.04618; AGENTS.md 2602.11988).

Context today is orchestrator-injected and stateless. ACE evolves a *context* (a playbook) from
outcomes: as the router solves tasks in a repo, it distils short, reusable lessons ("for this failure
signature, do X") into a per-repo playbook — an auto-maintained AGENTS.md — that is injected as a
context preamble on future tasks. The playbook is bounded and pruned (keep high-support, recent
lessons), so it sharpens rather than bloats (the AGENTS.md study's caution: bad context files hurt).

Deterministic, dependency-free. Ties memory -> context: lessons come from verified successes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Lesson:
    failure_signature: str
    rule: str               # short, imperative ("use repo_map; the constant lives in policy_*.py")
    support: int = 1        # how many verified successes back this lesson
    last_seen: float = 0.0


@dataclass
class RepoPlaybook:
    repo_family: str
    lessons: list[Lesson] = field(default_factory=list)
    max_lessons: int = 12

    def record_success(self, *, failure_signature: str, rule: str, now: float = 0.0) -> None:
        """Distil a verified success into a lesson (strengthen if already known); prune to bound."""
        for les in self.lessons:
            if les.failure_signature == failure_signature and les.rule == rule:
                les.support += 1
                les.last_seen = max(les.last_seen, now)
                return
        self.lessons.append(Lesson(failure_signature, rule, support=1, last_seen=now))
        self._prune()

    def _prune(self) -> None:
        # keep the strongest, most-recent lessons (ACE: refine, don't bloat)
        self.lessons.sort(key=lambda x: (x.support, x.last_seen), reverse=True)
        del self.lessons[self.max_lessons:]

    def render(self, *, failure_signature: str | None = None, max_lines: int = 8) -> str:
        """Render the playbook as a context preamble, surfacing signature-relevant lessons first."""
        ranked = sorted(self.lessons,
                        key=lambda x: (x.failure_signature == failure_signature, x.support, x.last_seen),
                        reverse=True)[:max_lines]
        if not ranked:
            return ""
        lines = [f"- ({x.failure_signature}) {x.rule}  [seen {x.support}x]" for x in ranked]
        return "## Repo playbook (auto-maintained from verified fixes)\n" + "\n".join(lines)

    def covers(self, failure_signature: str) -> bool:
        return any(x.failure_signature == failure_signature for x in self.lessons)
