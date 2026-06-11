# ruff: noqa: E501
"""Verifier-guided repair — climb the dense battery gradient instead of guessing at a binary oracle.

Same localize -> propose -> splice machinery as repair_v2, but two principled changes:
  1. The in-loop accept signal is the FAIR, CONTINUOUS `repair_battery` score (spec + public test +
     buggy baseline), never `task.hidden_test`. The hidden test is reserved strictly for grading by
     the caller (`replay_runner.verify`). This both fixes the privilege leak in repair_harness/repair_v2
     and gives the search a gradient to climb.
  2. Each proposal is conditioned on the battery's STRUCTURED feedback (which discriminating checks are
     still failing, which guard checks regressed), not just a single test's traceback.

`search_mode`:
  * "greedy" (Phase 0): repair_v2's best-of-k loop, ranking candidates by battery score and seeding the
    next round with the best candidate's feedback. Preserved unchanged as the comparison baseline.
  * "beam" (P7 W3): frontier of `beam_width` best nodes; each expands `k` children conditioned on its
    own battery feedback + a DIFFERENT strategy directive (repair_strategies, AutoVerus-style), so
    siblings explore different repair hypotheses rather than temperature noise.
  * "mcts" (P7 W3, VerMCTS 2402.08147): UCT with the battery score as an optimistic value; candidates
    that fail to parse / duplicate NEVER become nodes — the parent's failure counter is incremented and
    penalized in UCT; progressive widening (children < ceil(sqrt(visits))) bounds branching.

All modes share `_expand` (prompt -> LLM -> parse -> splice -> battery score) and the in-loop MODEL
LADDER: a flat best-score trajectory triggers `marginal_value_of_next_call` and escalation
gemini -> haiku -> sonnet (the G-phase finding: the cheap model cannot climb even a valid gradient).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from evals.issue_replay.repair_harness import (
    _class_table,
    _extract,
    _first_block,
    _func_table,
    _llm,
    _localize,
    _owning_class,
    _owning_classes,
    _parse_classes,
    _parse_funcs,
    _splice,
)
from evals.issue_replay.repair_v2 import (
    _CRITIC,
    _PROMPT,
    _ast_hash,
    _diff_cap,
    module_skeleton,
    sibling_signatures,
)
from evals.issue_replay.replay_task import IssueReplayTask

from acp.finops.marginal_value import marginal_value_of_next_call
from acp.verification.repair_battery import (
    BatteryScore,
    RepairBattery,
    build_battery,
    score_candidate,
)


@dataclass
class _Spec:
    issue_text: str
    public_test: str
    module_path: str


@dataclass
class GuidedResult:
    module_src: str
    cost_usd: float
    ran: bool
    telemetry: dict = field(default_factory=dict)


def _instr(whole: bool) -> str:
    return ("Return ONLY the full corrected module in a ```python code block." if whole else
            "Return ONLY the corrected full definition(s) of the function(s) shown, in a ```python "
            "code block — same names, same signatures, nothing else.")


# ---- in-loop model ladder (P7 W3) ----------------------------------------------------------------
# Solve-probability priors per rung, anchored on Phase-0 measurements (gemini flat on valid gradients,
# sonnet climbs). Hardcoded + logged so post-hoc calibration can replace them.
_RUNGS: tuple[tuple[str, str, tuple[float, float], float], ...] = (
    ("gemini", "gemini-3-flash-preview", (0.30e-6, 2.50e-6), 0.09),
    ("haiku", "claude-haiku-4-5", (1e-6, 5e-6), 0.15),
    ("sonnet", "claude-sonnet-4-6", (3e-6, 15e-6), 0.27),
)
_EST_ROUND_COST = {"gemini": 0.003, "haiku": 0.01, "sonnet": 0.04}   # ~k samples + critic
_FLAT_DELTA = 0.02


def _maybe_escalate(trajectory: list[float], rung_idx: int, spend: float) -> bool:
    """Escalate the in-loop model when the best-score trajectory has gone flat (the Phase-0 signature
    of a model below the gradient's capability floor) and the marginal value supports it."""
    if rung_idx >= len(_RUNGS) - 1 or len(trajectory) < 3:
        return False
    if trajectory[-1] - trajectory[-3] >= _FLAT_DELTA:
        return False
    nxt = _RUNGS[rung_idx + 1]
    mv = marginal_value_of_next_call(p_success_now=_RUNGS[rung_idx][3], p_success_after=nxt[3],
                                     call_cost=_EST_ROUND_COST[nxt[0]],
                                     budget_class="normal_bugfix", spend_so_far=spend)
    return mv.proceed


@dataclass
class _Ctx:
    """Shared expansion context (built once from the root) for all search modes."""
    spec: _Spec
    battery: RepairBattery
    bench: Path
    root_src: str
    focus_names: list[str]
    whole: bool
    class_mode: bool
    skeleton: str
    sib_block: str
    instr: str
    skill: str = ""


def _focus_for(ctx: _Ctx, src: str) -> tuple[dict[str, tuple[int, int, int]], str]:
    """Recompute the splice table + focus text for a NODE's source (spans move after each splice)."""
    if ctx.whole:
        return {}, src[:14000]
    ftab = _func_table(src)
    if ctx.class_mode:
        ctab = _class_table(src)
        owners = _owning_class(src)
        table = {**{n: ctab[n] for n in ctx.focus_names if n in ctab},
                 **{n: ftab[n] for n in ctx.focus_names if n in ftab and n not in owners}}
    else:
        table = {n: ftab[n] for n in ctx.focus_names if n in ftab}
    if not table:                      # focus vanished (heavy rewrite): fall back to the root's focus
        return _focus_for(ctx, ctx.root_src) if src != ctx.root_src else ({}, src[:14000])
    return table, _extract(src, list(table), table)


def _expand(ctx: _Ctx, parent_src: str, feedback: str, *, model_id: str, rate: tuple[float, float],
            temperature: float, directive_text: str = "", diagnosis: str = "",
            failed_block: str = "") -> tuple[str | None, float]:
    """One prompt->LLM->parse->splice expansion against the PARENT's source. Returns (cand|None, cost).
    None = provider error, unparseable output, or no spliceable definitions (VerMCTS: not a node)."""
    table, focus = _focus_for(ctx, parent_src)
    diag = (f"REVIEWER DIAGNOSIS (address this directly):\n{diagnosis}\n\n" if diagnosis else "")
    if directive_text:
        diag += f"STRATEGY FOR THIS ATTEMPT:\n{directive_text}\n\n"
    prompt = (ctx.skill + "\n\n" if ctx.skill else "") + _PROMPT.format(
        instr=ctx.instr, issue=ctx.spec.issue_text, skeleton=ctx.skeleton, siblings=ctx.sib_block,
        focus=focus, failure=feedback, diagnosis=diag, failed=failed_block)
    try:
        text, it, ot = _llm(model_id, prompt, temperature=temperature)
    except Exception:  # noqa: BLE001 - provider hiccup: a failed expansion, not a crash
        return None, 0.0
    cost = it * rate[0] + ot * rate[1]
    if ctx.whole:
        cand = _first_block(text)
    else:
        defs = {**_parse_funcs(text), **(_parse_classes(text) if ctx.class_mode else {})}
        defs = {n: s for n, s in defs.items() if n in table}
        cand = _splice(parent_src, table, defs) if defs else None
    return cand, cost


def guided_repair(task: IssueReplayTask, root: Path, *, model_id: str, rate: tuple[float, float],
                  client, search_mode: str = "greedy", k: int = 3, rounds: int = 3,
                  n_example: int = 8, n_property: int = 4, skill: str = "",
                  battery: RepairBattery | None = None, beam_width: int = 2,
                  max_expansions: int = 12, ladder: bool = False,
                  record_candidates: bool = False) -> GuidedResult:
    """Greedy verifier-guided repair. Returns the best-scoring candidate module (graded by the caller).

    NEVER reads task.hidden_test. Localization + the in-loop oracle use only the public test + spec +
    buggy baseline (the battery)."""
    root.mkdir(parents=True, exist_ok=True)
    bench = root / "battery_ws"
    bench.mkdir(parents=True, exist_ok=True)

    spec = _Spec(issue_text=f"{task.issue_title}\n{task.issue_body}", public_test=task.public_test,
                 module_path=task.module_path)
    if battery is None:
        battery = build_battery(spec, client=client, module_path=task.module_path,
                                extra_files=task.extra_files, baseline_src=task.buggy,
                                public_test=task.public_test, workspace_root=bench,
                                n_example=n_example, n_property=n_property)

    current = task.buggy
    table = _func_table(current)
    # FAIR localization: use the public (failing) test, never the hidden test.
    focus_names = _localize(current, task.issue_title, task.public_test, "")
    whole = not focus_names
    # P7 W2 class-scope promotion: a focused METHOD is repaired as its whole class (whole-class bugs
    # like OneToOne.update need cross-method context the lone-function splice never shows). Pure
    # functions keep the function-level path; the merged span table lets _splice handle both.
    # Methods defined on several classes are disambiguated by the class named in the issue title
    # ("fix OneToOne.update ..." -> OneToOne, not the first class that happens to define update).
    import re as _re
    title_ids = set(_re.findall(r"[A-Za-z_]\w*", task.issue_title))
    all_owners = _owning_classes(current)
    owners = {n: (next((c for c in cs if c in title_ids), cs[0]))
              for n, cs in all_owners.items()}
    cls_names = sorted({owners[n] for n in focus_names if n in owners})
    class_mode = bool(cls_names)
    if class_mode:
        ctab = _class_table(current)
        pure = [n for n in focus_names if n not in owners]
        focus_names = cls_names + pure
        table = {**{n: ctab[n] for n in cls_names if n in ctab},
                 **{n: table[n] for n in pure if n in table}}
        focus = _extract(current, [n for n in focus_names if n in table], table)
    else:
        focus = _extract(current, focus_names, table) if focus_names else current[:14000]
    skeleton = module_skeleton(current) or "(unavailable)"
    sibs = sibling_signatures(task.extra_files)
    sib_block = f"SIBLING MODULES (callable API):\n{sibs}\n\n" if sibs else ""
    instr = ("Return ONLY the corrected full definition(s) of the class(es)/function(s) shown, in a "
             "```python code block — same names, same signatures, nothing else."
             if class_mode else _instr(whole))

    ctx = _Ctx(spec=spec, battery=battery, bench=bench, root_src=current, focus_names=focus_names,
               whole=whole, class_mode=class_mode, skeleton=skeleton, sib_block=sib_block,
               instr=instr, skill=skill)
    if search_mode == "beam":
        return _beam(ctx, model_id=model_id, rate=rate, k=k, rounds=rounds, beam_width=beam_width,
                     max_expansions=max_expansions, ladder=ladder, record_candidates=record_candidates)
    if search_mode == "mcts":
        return _mcts(ctx, model_id=model_id, rate=rate, max_expansions=max_expansions,
                     ladder=ladder, record_candidates=record_candidates)

    base_score = score_candidate(battery, candidate_src=current, workspace_root=bench, candidate_id="base")
    best_cand, best_score = current, base_score
    cost = battery.gen_cost_usd
    ran = False
    diagnosis = ""
    failed_patches: list[str] = []
    seen = {_ast_hash(current)}
    trajectory = [base_score.score]
    n_expansions = 0
    scored: list[dict] = []   # (score, proxy_pass, src) per candidate — for value-function quality eval

    for rnd in range(rounds):
        feedback = best_score.feedback()
        diag_block = f"REVIEWER DIAGNOSIS (address this directly):\n{diagnosis}\n\n" if diagnosis else ""
        failed_block = ("PATCHES THAT ALREADY FAILED — do NOT repeat these approaches:\n"
                        + "\n---\n".join(failed_patches[-3:]) + "\n") if failed_patches else ""
        prompt = (skill + "\n\n" if skill else "") + _PROMPT.format(
            instr=instr, issue=spec.issue_text, skeleton=skeleton, siblings=sib_block, focus=focus,
            failure=feedback, diagnosis=diag_block, failed=failed_block)
        temps = [0.0, 0.7, 1.0] if rnd == 0 else [0.4, 0.8, 1.0]
        round_best_diff = ""
        for i in range(k):
            try:
                text, it, ot = _llm(model_id, prompt, temperature=temps[min(i, len(temps) - 1)])
            except Exception:  # noqa: BLE001 - provider hiccup: skip the sample
                continue
            ran = True
            cost += it * rate[0] + ot * rate[1]
            if whole:
                cand = _first_block(text) or current
            else:
                defs = {**_parse_funcs(text), **(_parse_classes(text) if class_mode else {})}
                defs = {n: s for n, s in defs.items() if n in table}   # only spliceable spans
                cand = _splice(current, table, defs) if defs else current
            h = _ast_hash(cand)
            if not h or h in seen:                 # early prune: unparseable or already-tried
                continue
            seen.add(h)
            n_expansions += 1
            sc = score_candidate(battery, candidate_src=cand, workspace_root=bench,
                                 candidate_id=f"r{rnd}s{i}", diff=_diff_cap(task.buggy, cand))
            if record_candidates:
                scored.append({"score": round(sc.score, 4), "proxy_pass": sc.proxy_pass, "src": cand})
            if sc.score > best_score.score:
                best_cand, best_score = cand, sc
                round_best_diff = _diff_cap(task.buggy, cand)
            if sc.score < 1.0:                     # a not-yet-perfect candidate is a "failed" approach
                failed_patches.append(_diff_cap(task.buggy, cand) or "(no-op patch)")
        trajectory.append(best_score.score)
        if best_score.proxy_pass:                  # battery fully satisfied -> stop early (fair stop)
            break
        # critic round (reuse repair_v2._CRITIC) keyed to the best candidate's battery feedback
        if rnd < rounds - 1 and round_best_diff:
            try:
                diagnosis, it, ot = _llm(model_id, _CRITIC.format(
                    issue=task.issue_title, focus=focus, diff=round_best_diff, failure=best_score.feedback()),
                    temperature=0.2)
                cost += it * rate[0] + ot * rate[1]
            except Exception:  # noqa: BLE001
                diagnosis = ""

    telemetry = {
        "search_mode": search_mode, "focus_names": focus_names, "whole_module": whole,
        "class_mode": class_mode,
        "n_checks": len(battery.checks), "n_discriminating": battery.n_discriminating,
        "n_guard": battery.n_guard, "n_expansions": n_expansions,
        "best_score": round(best_score.score, 4), "best_proxy_pass": best_score.proxy_pass,
        "best_accept": best_score.accept(), "battery_valid": battery.valid,
        "score_trajectory": [round(s, 4) for s in trajectory],
        "gen_cost_usd": round(battery.gen_cost_usd, 6),
    }
    if record_candidates:
        telemetry["candidates"] = scored
    return GuidedResult(module_src=best_cand, cost_usd=round(cost, 6), ran=ran, telemetry=telemetry)


def _rung_for(model_id: str) -> int:
    for i, (_k, mid, _r, _p) in enumerate(_RUNGS):
        if mid == model_id:
            return i
    return 0


def _select_final(pool: list[tuple[str, BatteryScore]]) -> tuple[str, BatteryScore]:
    """Kimi-Dev-style selection (W4): accept() first, then reproduction-fixed x regression-kept,
    then raw score — over the final frontier/tree instead of single best score."""
    return max(pool, key=lambda p: (p[1].accept(), p[1].disc_frac * p[1].guard_frac, p[1].score))


def _telemetry(mode: str, ctx: _Ctx, best: BatteryScore, trajectory: list[float], n_exp: int,
               escalations: list[dict], extra: dict | None = None) -> dict:
    return {"search_mode": mode, "focus_names": ctx.focus_names, "whole_module": ctx.whole,
            "class_mode": ctx.class_mode, "n_checks": len(ctx.battery.checks),
            "n_discriminating": ctx.battery.n_discriminating, "n_guard": ctx.battery.n_guard,
            "n_expansions": n_exp, "best_score": round(best.score, 4),
            "best_proxy_pass": best.proxy_pass, "best_accept": best.accept(),
            "battery_valid": ctx.battery.valid, "escalations": escalations,
            "score_trajectory": [round(s, 4) for s in trajectory],
            "gen_cost_usd": round(ctx.battery.gen_cost_usd, 6), **(extra or {})}


def _beam(ctx: _Ctx, *, model_id: str, rate: tuple[float, float], k: int, rounds: int,
          beam_width: int, max_expansions: int, ladder: bool,
          record_candidates: bool) -> GuidedResult:
    """Frontier search: each beam node expands k children conditioned on ITS OWN battery feedback +
    a distinct strategy directive; keep the top `beam_width` of frontier+children by score."""
    from evals.issue_replay.repair_strategies import categorize, directive
    rung = _rung_for(model_id)
    base = score_candidate(ctx.battery, candidate_src=ctx.root_src, workspace_root=ctx.bench,
                           candidate_id="base")
    frontier: list[tuple[str, BatteryScore]] = [(ctx.root_src, base)]
    best = (ctx.root_src, base)
    seen = {_ast_hash(ctx.root_src)}
    cost = ctx.battery.gen_cost_usd
    ran = False
    n_exp = 0
    trajectory = [base.score]
    escalations: list[dict] = []
    failed: list[str] = []
    scored: list[dict] = []
    temps = [0.0, 0.7, 1.0]
    for rnd in range(rounds):
        children: list[tuple[str, BatteryScore]] = []
        for node_src, node_sc in frontier:
            if n_exp >= max_expansions:
                break
            cat = categorize(node_sc, node_sc.feedback())
            fail_block = ("PATCHES THAT ALREADY FAILED — do NOT repeat these approaches:\n"
                          + "\n---\n".join(failed[-3:]) + "\n") if failed else ""
            for i in range(k):
                if n_exp >= max_expansions:
                    break
                cand, c = _expand(ctx, node_src, node_sc.feedback(), model_id=model_id, rate=rate,
                                  temperature=temps[min(i, 2)], directive_text=directive(cat, i),
                                  failed_block=fail_block)
                cost += c
                if c:
                    ran = True
                h = _ast_hash(cand) if cand else ""
                if not cand or not h or h in seen:
                    continue
                seen.add(h)
                n_exp += 1
                sc = score_candidate(ctx.battery, candidate_src=cand, workspace_root=ctx.bench,
                                     candidate_id=f"b{rnd}_{n_exp}",
                                     diff=_diff_cap(ctx.root_src, cand))
                if record_candidates:
                    scored.append({"score": round(sc.score, 4), "proxy_pass": sc.proxy_pass,
                                   "accept": sc.accept(), "src": cand})
                children.append((cand, sc))
                if sc.score < 1.0:
                    failed.append(_diff_cap(ctx.root_src, cand) or "(no-op patch)")
        frontier = sorted(frontier + children, key=lambda p: -p[1].score)[:beam_width]
        if frontier[0][1].score > best[1].score:
            best = frontier[0]
        trajectory.append(best[1].score)
        if best[1].accept() or best[1].proxy_pass or n_exp >= max_expansions:
            break
        if ladder and _maybe_escalate(trajectory, rung, cost):
            rung += 1
            escalations.append({"round": rnd, "to": _RUNGS[rung][0], "spend": round(cost, 4)})
            model_id, rate = _RUNGS[rung][1], _RUNGS[rung][2]
    best = _select_final(frontier + [best])
    tel = _telemetry("beam", ctx, best[1], trajectory, n_exp, escalations,
                     {"beam_width": beam_width})
    if record_candidates:
        tel["candidates"] = scored
    return GuidedResult(module_src=best[0], cost_usd=round(cost, 6), ran=ran, telemetry=tel)


@dataclass
class _Node:
    src: str
    score: BatteryScore
    parent: _Node | None = None
    children: list[_Node] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0
    failures: int = 0       # VerMCTS: unparseable/dup expansions never become nodes — counted here


def _uct(parent: _Node, child: _Node, c: float = 1.4) -> float:
    n = child.visits + child.failures or 1
    return child.value / n + c * math.sqrt(math.log(parent.visits + 1) / n)


def _mcts(ctx: _Ctx, *, model_id: str, rate: tuple[float, float], max_expansions: int,
          ladder: bool, record_candidates: bool) -> GuidedResult:
    """VerMCTS-style tree search: battery score = optimistic leaf value, backpropagated; progressive
    widening (children < ceil(sqrt(visits))) re-expands promising regions instead of exploding."""
    from evals.issue_replay.repair_strategies import categorize, directive
    rung = _rung_for(model_id)
    base = score_candidate(ctx.battery, candidate_src=ctx.root_src, workspace_root=ctx.bench,
                           candidate_id="base")
    root = _Node(src=ctx.root_src, score=base, visits=1, value=base.score)
    all_nodes = [root]
    seen = {_ast_hash(ctx.root_src)}
    cost = ctx.battery.gen_cost_usd
    ran = False
    n_exp = 0
    trajectory = [base.score]
    escalations: list[dict] = []
    scored: list[dict] = []
    best = root
    while n_exp < max_expansions:
        # SELECT: descend by UCT until progressive widening admits a new child
        node = root
        while node.children and len(node.children) >= max(1, math.ceil(math.sqrt(node.visits))):
            node = max(node.children, key=lambda ch: _uct(node, ch))
        # EXPAND: strategy directive cycles over the node's previous attempts (children + failures)
        cat = categorize(node.score, node.score.feedback())
        attempt = len(node.children) + node.failures
        temp = [0.0, 0.7, 1.0][attempt % 3]
        cand, c = _expand(ctx, node.src, node.score.feedback(), model_id=model_id, rate=rate,
                          temperature=temp, directive_text=directive(cat, attempt))
        cost += c
        if c:
            ran = True
        n_exp += 1
        h = _ast_hash(cand) if cand else ""
        if not cand or not h or h in seen:
            node.failures += 1          # VerMCTS: no node for a failed program; penalize the parent
            node.visits += 1
            continue
        seen.add(h)
        sc = score_candidate(ctx.battery, candidate_src=cand, workspace_root=ctx.bench,
                             candidate_id=f"m{n_exp}", diff=_diff_cap(ctx.root_src, cand))
        if record_candidates:
            scored.append({"score": round(sc.score, 4), "proxy_pass": sc.proxy_pass,
                           "accept": sc.accept(), "src": cand})
        child = _Node(src=cand, score=sc, parent=node)
        node.children.append(child)
        all_nodes.append(child)
        # BACKPROP the battery value
        cur: _Node | None = child
        while cur is not None:
            cur.visits += 1
            cur.value += sc.score
            cur = cur.parent
        if sc.score > best.score.score:
            best = child
        trajectory.append(best.score.score)
        if sc.accept() or sc.proxy_pass:
            best = child
            break
        if ladder and n_exp % 4 == 0 and _maybe_escalate(trajectory, rung, cost):
            rung += 1
            escalations.append({"expansion": n_exp, "to": _RUNGS[rung][0], "spend": round(cost, 4)})
            model_id, rate = _RUNGS[rung][1], _RUNGS[rung][2]
    pick_src, pick_sc = _select_final([(n.src, n.score) for n in all_nodes])
    tel = _telemetry("mcts", ctx, pick_sc, trajectory, n_exp, escalations,
                     {"n_nodes": len(all_nodes),
                      "total_failures": sum(n.failures for n in all_nodes)})
    if record_candidates:
        tel["candidates"] = scored
    return GuidedResult(module_src=pick_src, cost_usd=round(cost, 6), ran=ran, telemetry=tel)
