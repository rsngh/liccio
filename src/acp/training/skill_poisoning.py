"""Skill poisoning defense (Alpha 21 WS12).

A learned/proposed skill is text injected into a frozen agent's context every step — a
prime vector for harness-evolution attacks. Before a skill can reach candidate deployment
it is scanned for least-privilege violations: secret exfiltration, test disabling,
verifier weakening, unsafe network, broad destructive rewrites, policy bypass, private-repo
leakage, and hidden prompt injection. Any hit blocks deployment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# category -> list of (compiled pattern, human description)
_THREATS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "secret_exfiltration": [
        (re.compile(r"exfiltrat", re.I), "exfiltration directive"),
        (re.compile(r"(send|post|upload).{0,30}(api[_ ]?key|secret|token|credential)", re.I),
         "send secrets externally"),
        (re.compile(r"base64.{0,20}(env|secret|key)", re.I), "encode-and-leak secrets"),
    ],
    "test_disabling": [
        (re.compile(r"(skip|disable|delete|remove|comment out).{0,20}test", re.I),
         "disable/remove tests"),
        (re.compile(r"--no-verify|pytest.{0,10}--co\b", re.I), "bypass test verification"),
        (re.compile(r"\bxfail\b.{0,20}(all|every)", re.I), "xfail everything"),
    ],
    "verifier_weakening": [
        (re.compile(r"(disable|skip|weaken|bypass|lower).{0,25}(verif|validat|check)", re.I),
         "weaken the verifier"),
    ],
    "unsafe_network": [
        (re.compile(r"\b(curl|wget|nc -e)\b.{0,20}https?://", re.I), "raw network call"),
        (re.compile(r"requests\.(get|post)\(\s*['\"]https?://", re.I), "external http request"),
        (re.compile(r"open.{0,10}socket|socket\.connect", re.I), "open a socket"),
    ],
    "broad_rewrite": [
        (re.compile(r"rm\s+-rf|delete (all|every)|rewrite the (entire|whole)", re.I),
         "destructive broad rewrite"),
    ],
    "policy_bypass": [
        (re.compile(r"ignore (the |all )?(previous|prior|safety|rules|policy)", re.I),
         "policy bypass"),
        (re.compile(r"override (safety|the guard)", re.I), "override safety"),
    ],
    "private_repo_leakage": [
        (re.compile(r"(copy|upload|push|send).{0,25}(repo|codebase|source).{0,25}"
                    r"(external|elsewhere|http)", re.I), "leak private repo"),
    ],
    "prompt_injection": [
        (re.compile(r"disregard.{0,20}instruction|you are now (a|an)\b", re.I),
         "hidden prompt injection"),
    ],
}


@dataclass
class SkillPoisonScan:
    safe: bool
    findings: list[dict] = field(default_factory=list)  # {category, detail, match}

    @property
    def categories(self) -> set[str]:
        return {f["category"] for f in self.findings}


def scan_skill(content: str) -> SkillPoisonScan:
    """Scan skill content for poisoning patterns; ``safe`` is False on any hit."""
    findings: list[dict] = []
    for category, patterns in _THREATS.items():
        for pat, desc in patterns:
            m = pat.search(content)
            if m:
                findings.append({"category": category, "detail": desc,
                                 "match": m.group(0)[:80]})
    return SkillPoisonScan(safe=not findings, findings=findings)
