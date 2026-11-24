"""Demonstrates the task package as an *evaluation instrument* for coding systems.

Simulates four 'candidate solutions' for one packaged task and grades each with the real grader:
  reference      -> must be RESOLVED
  one-rule-short -> the typical LLM failure (forgets one requirement): UNRESOLVED, per-rule breakdown shows which
  empty          -> UNRESOLVED
  test-tampering -> REJECTED (agent tried to edit the protected tests)
Usage: python scripts/demo_eval.py tasks/click/duration-03
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from taskfactory.core import Variant, Workspace
from taskfactory.recipes import ALL
from taskfactory.adapters import get_adapter
from taskfactory.factory import evaluate


def main(task_dir):
    td = Path(task_dir)
    t = json.loads((td / "task.json").read_text()); vj = json.loads((td / "variant.json").read_text())
    recipe = ALL[t["repo"]["name"]][vj["family"]]
    v = Variant(vj["family"], vj["seed"], vj["rules"], vj["params"])
    ad = get_adapter(t["repo"]["language"])
    ws = Workspace(t["repo"]["name"])

    def patch_for(rules):
        ws.reset(); ws.apply(recipe.impl_edits(v, set(rules))); return ws.diff()

    cands = {"reference solution": (td / "reference.patch").read_text()}
    for rid, (rules, dropped) in list(recipe.ablation_sets(v).items())[:2]:
        cands[f"plausible solution missing requirement '{rid}'"] = patch_for(rules)
    cands["empty patch"] = ""
    cands["tampers with protected tests"] = "diff --git a/{0} b/{0}\n--- a/{0}\n+++ b/{0}\n@@ -0,0 +1 @@\n+x\n".format(
        __import__("re").findall(r"^diff --git a/(\S+)", (td / "tests.patch").read_text(), __import__("re").M)[0])
    out = {}
    for name, p in cands.items():
        r = evaluate(td, p, ad); out[name] = r
        print(f"{name:55} -> {r['verdict']:10} F2P {r.get('fail_to_pass','-'):>7}  P2P {r.get('pass_to_pass','-'):>10}  "
              f"{r.get('per_rule', r.get('reason',''))}")
    (td / "demo_eval.json").write_text(json.dumps(out, indent=2))


main(sys.argv[1])
