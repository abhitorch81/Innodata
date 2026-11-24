"""Packaging, cross-task variation analysis, candidate evaluation and reporting."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from .adapters.base import rule_of
from .core import ROOT, REPOS, Workspace, sh
from .validate import validate

TASKS = ROOT / "tasks"
REPO_URLS = {"click": "https://github.com/pallets/click", "zod": "https://github.com/colinhacks/zod",
             "jsoncpp": "https://github.com/open-source-parsers/jsoncpp"}
SCHEMA = "taskfactory/1"


def difficulty(ev, v):
    """Transparent heuristic, not a calibrated claim."""
    s = len(v.rules) + ev["ref_patch_lines"] / 25 + 1.5 * len([f for f in ev["files_touched"]]) \
        + (2 if ev["stages"]["S6_regression_guard"].get("applicable") else 0)
    return "easy" if s < 9 else "medium" if s < 14 else "hard"


def package(recipe, v, ev, adapter_info) -> Path:
    d = TASKS / recipe.repo / v.id
    d.mkdir(parents=True, exist_ok=True)
    art = ev.pop("_artifacts")
    (d / "reference.patch").write_text(art["ref_patch"])
    (d / "tests.patch").write_text(art["tests_patch"])
    (d / "PROBLEM.md").write_text(recipe.requirements_md(v))
    f2p = ev.pop("fail_to_pass"); p2p = ev.pop("pass_to_pass")
    (d / "fail_to_pass.txt").write_text("\n".join(f2p) + "\n")
    (d / "pass_to_pass.txt").write_text("\n".join(p2p) + "\n")
    task = {
        "schema": SCHEMA, "task_id": f"{recipe.repo}/{v.id}", "title": recipe.title(v),
        "repo": {"name": recipe.repo, "url": REPO_URLS[recipe.repo], "base_commit": Workspace(recipe.repo).base,
                 "language": adapter_info["lang"]},
        "problem_statement": "PROBLEM.md",
        "reference_patch": "reference.patch", "test_patch": "tests.patch",
        "fail_to_pass": "fail_to_pass.txt", "pass_to_pass": "pass_to_pass.txt",
        "fail_to_pass_count": len(f2p), "pass_to_pass_count": len(p2p),
        "commands": adapter_info["commands"],
        "family": recipe.family, "rules": [{"id": r, "title": recipe.rule(r).title} for r in v.rules],
        "difficulty": difficulty(ev, v),
        "validation": "validation.json",
    }
    (d / "variant.json").write_text(json.dumps({"family": v.family, "seed": v.seed, "rules": v.rules,
                                                "params": v.params}, indent=2) + "\n")
    task["variant"] = "variant.json"
    (d / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    (d / "validation.json").write_text(json.dumps(ev, indent=2) + "\n")
    return d


def variation_matrix(recipe, variants, adapter, log=print):
    """cells[i][j] = fraction of task i's feature tests passed by task j's reference implementation.
    Diagonal must be 1.0; off-diagonal < 1 proves the tasks demand *different behaviour*."""
    ws = Workspace(recipe.repo)
    n = len(variants)
    M = [[None] * n for _ in range(n)]
    for j, vj in enumerate(variants):
        for i, vi in enumerate(variants):
            ws.reset(); adapter.prepare(ws)
            ws.apply(recipe.impl_edits(vj, set(vj.rules)))
            ws.apply(recipe.test_edits(vi))
            r = adapter.run_feature(ws, vi, recipe)
            M[i][j] = round(len(r.passed) / max(1, r.total), 3) if r.build_ok else 0.0
        log(f"  variation: reference of {vj.id} evaluated against all {n} test-suites")
    return M


def evaluate(task_dir: Path, candidate_patch: str, adapter, log=print):
    """Grade a candidate patch (from any coding system) against a packaged task.

    RESOLVED = every fail-to-pass test passes AND every pass-to-pass test still passes.
    Also returns per-requirement (rule) scores, so partial solutions are distinguishable."""
    import re
    from .core import Variant
    from .recipes import ALL
    t = json.loads((task_dir / "task.json").read_text())
    vj = json.loads((task_dir / "variant.json").read_text())
    recipe = ALL[t["repo"]["name"]][vj["family"]]
    v = Variant(vj["family"], vj["seed"], vj["rules"], vj["params"])
    tests_patch = (task_dir / "tests.patch").read_text()
    protected = set(re.findall(r"^diff --git a/(\S+)", tests_patch, re.M))
    touched = set(re.findall(r"^diff --git a/(\S+)", candidate_patch, re.M))
    if protected & touched:
        return {"verdict": "REJECTED", "reason": f"candidate edits protected test files: {sorted(protected & touched)}"}
    ws = Workspace(t["repo"]["name"]); ws.reset(); adapter.prepare(ws)
    try:
        ws.apply_patch(candidate_patch)
    except RuntimeError as e:
        return {"verdict": "REJECTED", "reason": str(e)[:300]}
    ws.apply_patch(tests_patch)
    rf = adapter.run_feature(ws, v, recipe)
    rr = adapter.run_regression(ws, v, recipe, full=True)
    f2p = set((task_dir / "fail_to_pass.txt").read_text().split())
    p2p = set((task_dir / "pass_to_pass.txt").read_text().split())
    per_rule = {}
    for tid in f2p:
        k = rule_of(tid) or "?"
        per_rule.setdefault(k, [0, 0])[1] += 1
        per_rule[k][0] += tid in rf.passed
    res = {"fail_to_pass": f"{len(f2p & rf.passed)}/{len(f2p)}", "pass_to_pass": f"{len(p2p & rr.passed)}/{len(p2p)}",
           "per_rule": {k: f"{a}/{b}" for k, (a, b) in sorted(per_rule.items())}, "build_ok": rf.build_ok}
    res["verdict"] = "RESOLVED" if f2p <= rf.passed and p2p <= rr.passed else "UNRESOLVED"
    return res
