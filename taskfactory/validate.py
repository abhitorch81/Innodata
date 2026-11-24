"""Validation pipeline: turns a Variant into *evidence* that the task is solvable, discriminating
and regression-safe. Every stage is independently reported (no single opaque 'valid' bit)."""
from __future__ import annotations
import json
import re
import time
from pathlib import Path

from .adapters.base import rule_of
from .core import Edit, Workspace, AnchorError
from .mutate import edit_mutants, line_mutants, _is_comment

STAGES = ["S1_base_fails", "S2_reference_passes", "S3_regression_intact", "S4_rule_ablations",
          "S5_mutation_kill", "S6_regression_guard", "S7_determinism"]


def _tags(ids):
    return {i: rule_of(i) for i in ids}


def context_mutants(ws_root: Path, impl_edits, lang, limit=10, radius=12, seed=0):
    """Mutate PRE-EXISTING lines adjacent to where the reference patch edits existing files.
    These model 'feature work that quietly breaks neighbouring behaviour'."""
    import random
    out = []
    for e in impl_edits:
        if e.kind in ("create", "append") or e.role != "impl":
            continue
        src = (ws_root / e.path).read_text() if (ws_root / e.path).exists() else ""
        # `ws_root` is a *reset* workspace -> original text
        i = src.find(e.anchor)
        if i < 0:
            continue
        lines = src.split("\n")
        ln = src[:i].count("\n")
        for k in range(max(0, ln - radius), min(len(lines), ln + radius)):
            line = lines[k]
            if _is_comment(line, lang) or src.count(line) != 1 or line.strip() in e.anchor:
                continue
            for name, new in line_mutants(line, lang):
                out.append((f"{e.path}:{k + 1} {name}: `{line.strip()[:60]}` -> `{new.strip()[:60]}`",
                            Edit(e.path, "replace", new, anchor=line, role="ctx")))
    random.Random(seed).shuffle(out)
    return out[:limit]


def validate(recipe, v, adapter, n_mutants=30, n_ctx=8, log=print):
    ws = Workspace(recipe.repo)
    full = set(v.rules)
    impl = recipe.impl_edits(v, full)
    tests = recipe.test_edits(v)
    ev = {"variant": v.id, "rules": v.rules, "stages": {}}
    t0 = time.time()

    def fresh():
        ws.reset(); adapter.prepare(ws)

    # ---- S1: tests alone on the base commit must fail (fail-to-pass)
    fresh(); ws.apply(tests)
    r = adapter.run_feature(ws, v, recipe)
    failing_tags = {rule_of(t) for t in r.failed}
    uncovered = [x for x in v.rules if x not in failing_tags]
    # every requirement must have >=1 test that FAILS on the base commit (fail-to-pass). Negative-behaviour tests
    # ("must stay as before") legitimately pass on base: they are kept as pass-to-pass *guard* tests.
    s1_ok = (not r.build_ok) or (not uncovered and bool(r.failed))
    guards = sorted(r.passed)
    ev["stages"]["S1_base_fails"] = dict(
        ok=s1_ok, mode="build/import error" if not r.build_ok else "assertion failures",
        failing=len(r.failed), guard_tests_passing_on_base=len(guards), rules_without_failing_test=uncovered)
    log(f"  S1 base fails            {'PASS' if s1_ok else 'FAIL'} ({ev['stages']['S1_base_fails']['mode']}, "
        f"{len(guards)} guard tests already pass)")

    # ---- reference patch + tests patch (the package artefacts)
    fresh(); ws.apply(impl); ref_patch = ws.diff()
    ws.apply(tests)
    full_patch = ws.diff()
    fresh(); ws.apply(tests); tests_patch = ws.diff()
    ev["ref_patch_lines"] = sum(1 for l in ref_patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
    ev["files_touched"] = re.findall(r"^diff --git a/(\S+)", ref_patch, re.M)

    # ---- S2/S3: reference passes feature tests AND the existing suite is intact
    fresh(); ws.apply(impl); ws.apply(tests)
    rf = adapter.run_feature(ws, v, recipe)
    ev["stages"]["S2_reference_passes"] = dict(ok=rf.ok, passed=len(rf.passed), failed=sorted(rf.failed),
                                               tail="" if rf.ok else rf.tail)
    log(f"  S2 reference passes      {'PASS' if rf.ok else 'FAIL'} ({len(rf.passed)} feature tests)")
    rr = adapter.run_regression(ws, v, recipe, full=True)
    base_ok = recipe._baseline.get(recipe.repo)
    ev["stages"]["S3_regression_intact"] = dict(ok=rr.ok, passed=len(rr.passed), failed=sorted(rr.failed)[:10],
                                                baseline_passed=base_ok)
    log(f"  S3 regression intact     {'PASS' if rr.ok else 'FAIL'} ({len(rr.passed)} existing tests)")
    # runners may not honour --exclude for every sub-project: never count the task's own tests as "existing" ones
    own = tuple(p + "::" for p in recipe.feature_test_paths(v))
    existing = {i for i in rr.passed if not i.startswith(own)}
    ev["fail_to_pass"] = sorted(rf.passed - set(guards))
    ev["pass_to_pass"] = sorted(existing | set(guards))

    # ---- S4: every rule, when removed, must be caught by tests attributed to that rule
    abl = {}
    for rid, (rules, dropped) in recipe.ablation_sets(v).items():
        fresh(); ws.apply(recipe.impl_edits(v, rules)); ws.apply(tests)
        ra = adapter.run_feature(ws, v, recipe)
        tg = _tags(ra.failed)
        hit = [t for t, g in tg.items() if g in dropped]
        abl[rid] = dict(dropped=sorted(dropped), caught=bool(hit), caught_by=len(hit),
                        collateral=len([1 for g in tg.values() if g not in dropped]), build_ok=ra.build_ok)
    ev["stages"]["S4_rule_ablations"] = dict(ok=all(a["caught"] for a in abl.values()), per_rule=abl)
    log("  S4 rule ablations        " + ("PASS" if ev["stages"]["S4_rule_ablations"]["ok"] else "FAIL") +
        "  " + " ".join(f"{k}:{'✓' if a['caught'] else '✗'}" for k, a in abl.items()))

    # ---- S5: patch-level mutation testing of the reference implementation
    killed = survived = invalid = 0
    survivors, kills_by_reg = [], 0
    for label, es in edit_mutants(impl, adapter.lang, seed=v.seed, limit=n_mutants):
        fresh()
        try:
            ws.apply(es)
        except AnchorError:
            invalid += 1; continue
        ws.apply(tests)
        rm = adapter.run_feature(ws, v, recipe)
        if not rm.build_ok and adapter.lang != "python":
            invalid += 1; continue  # stillborn mutant (does not compile)
        if rm.failed or not rm.build_ok:
            killed += 1
        else:
            rg = adapter.run_regression(ws, v, recipe, full=False)
            if rg.failed:
                killed += 1; kills_by_reg += 1
            else:
                survived += 1; survivors.append(label)
    tot = killed + survived
    score = killed / tot if tot else 1.0
    ev["stages"]["S5_mutation_kill"] = dict(ok=score >= 0.80, score=round(score, 3), killed=killed,
                                            killed_by_regression_only=kills_by_reg, survived=survived,
                                            invalid=invalid, survivors=survivors[:12])
    log(f"  S5 mutation kill         {'PASS' if score >= 0.8 else 'WARN'} {killed}/{tot} killed ({score:.0%}), {invalid} invalid")

    # ---- S6: regression guard - do existing tests catch breakage of pre-existing neighbours?
    fresh()
    ctx = context_mutants(ws.root, impl, adapter.lang, limit=n_ctx, seed=v.seed)
    if not ctx:
        ev["stages"]["S6_regression_guard"] = dict(ok=True, applicable=False,
                                                   note="purely additive patch - no pre-existing code touched")
        log("  S6 regression guard      n/a (additive patch)")
    else:
        ke = kf = sv = inv = 0; surv = []
        for label, me in ctx:
            fresh(); ws.apply(impl)
            try:
                ws.apply([me])
            except AnchorError:
                inv += 1; continue
            ws.apply(tests)
            rg = adapter.run_regression(ws, v, recipe, full=False)
            if rg.failed or not rg.build_ok:
                ke += 1; continue
            rf2 = adapter.run_feature(ws, v, recipe)
            if rf2.failed:
                kf += 1
            else:
                sv += 1; surv.append(label)
        tot = ke + kf + sv
        sc = (ke + kf) / tot if tot else 1.0
        ev["stages"]["S6_regression_guard"] = dict(ok=sc >= 0.6, applicable=True, score=round(sc, 3),
                                                   killed_by_existing_suite=ke, killed_by_feature_tests=kf,
                                                   survived=sv, invalid=inv, survivors=surv[:8])
        log(f"  S6 regression guard      {'PASS' if sc >= 0.6 else 'WARN'} {ke + kf}/{tot} neighbour-mutants caught "
            f"({ke} by existing suite)")

    # ---- S7: determinism
    fresh(); ws.apply(impl); ws.apply(tests)
    a = adapter.run_feature(ws, v, recipe); b = adapter.run_feature(ws, v, recipe)
    ev["stages"]["S7_determinism"] = dict(ok=(a.passed == b.passed and a.ok))
    log(f"  S7 determinism           {'PASS' if ev['stages']['S7_determinism']['ok'] else 'FAIL'}")

    gate = ["S1_base_fails", "S2_reference_passes", "S3_regression_intact", "S4_rule_ablations", "S7_determinism"]
    ev["valid"] = all(ev["stages"][s]["ok"] for s in gate)
    ev["seconds"] = round(time.time() - t0, 1)
    ev["_artifacts"] = dict(ref_patch=ref_patch, tests_patch=tests_patch)
    return ev
