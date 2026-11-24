"""CLI:  python -m taskfactory build|evaluate|list ..."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .core import Workspace
from .recipes import ALL
from .adapters import get_adapter
from .validate import validate
from .factory import package, variation_matrix, evaluate, TASKS


def main(argv=None):
    ap = argparse.ArgumentParser(prog="taskfactory")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="sample -> render -> validate -> package")
    b.add_argument("--repo", required=True); b.add_argument("--family", required=True)
    b.add_argument("-n", type=int, default=4); b.add_argument("--seed", type=int, default=0)
    b.add_argument("--mutants", type=int, default=30); b.add_argument("--no-matrix", action="store_true")
    e = sub.add_parser("evaluate", help="grade a candidate patch against a packaged task")
    e.add_argument("task_dir"); e.add_argument("patch")
    sub.add_parser("list"); sub.add_parser("report")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        for repo, fams in ALL.items():
            for f, r in fams.items():
                print(f"{repo:8} {f:14} {r.summary}")
        return 0
    if a.cmd == "report":
        from .report import render
        print("report: %d tasks, %d valid -> report.html, REPORT.md" % render()); return 0
    if a.cmd == "evaluate":
        td = Path(a.task_dir); t = json.loads((td / "task.json").read_text())
        ad = get_adapter(t["repo"]["language"])
        res = evaluate(td, Path(a.patch).read_text(), ad)
        print(json.dumps(res, indent=2)); return 0 if res["verdict"] == "RESOLVED" else 1

    recipe = ALL[a.repo][a.family]
    ad = get_adapter(recipe_lang(a.repo))
    ws = Workspace(a.repo); ws.reset(); ad.prepare(ws)
    base = ad.run_regression(ws, None, type("S", (), {"feature_test_paths": staticmethod(lambda v: [])}), full=True)
    print(f"[{a.repo}] baseline @ {ws.base[:10]}: {len(base.passed)} existing tests pass, {len(base.failed)} fail")
    recipe._baseline = {a.repo: len(base.passed)}
    variants = recipe.sample(a.n, a.seed)
    results = []
    for v in variants:
        print(f"\n== {a.repo}/{v.id}  rules={v.rules}")
        ev = validate(recipe, v, ad, n_mutants=a.mutants)
        d = package(recipe, v, ev, {"lang": ad.lang, "commands": ad.commands(recipe, v)})
        print(f"  -> {d}  valid={ev['valid']}  ({ev['seconds']}s)")
        results.append((v, ev))
    if not a.no_matrix and len(variants) > 1:
        print("\n== cross-task variation matrix")
        M = variation_matrix(recipe, variants, ad)
        out = TASKS / a.repo / f"_variation_{a.family}.json"
        out.write_text(json.dumps({"variants": [v.id for v in variants], "tests_i_vs_reference_j": M}, indent=2))
        for row in M:
            print("  ", " ".join(f"{x:5.2f}" for x in row))
    return 0


def recipe_lang(repo):
    return {"click": "python", "zod": "ts", "jsoncpp": "cpp"}[repo]


if __name__ == "__main__":
    sys.exit(main())
