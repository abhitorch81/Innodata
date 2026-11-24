"""Collect packaged tasks into one JSON document for the visual app."""
from __future__ import annotations
import json
import re
from pathlib import Path

from .adapters.base import rule_of
from .recipes import ALL

STAGES = ["S1_base_fails", "S2_reference_passes", "S3_regression_intact", "S4_rule_ablations",
          "S5_mutation_kill", "S6_regression_guard", "S7_determinism"]


def _task(d: Path) -> dict:
    t = json.loads((d / "task.json").read_text()); ev = json.loads((d / "validation.json").read_text())
    md = (d / "PROBLEM.md").read_text()
    reqs = re.findall(r"^\d+\. \*\*(.+?)\.\*\* (.*)$", md, re.M)
    rules = []
    for i, r in enumerate(t["rules"]):
        rules.append({"id": r["id"], "title": r["title"], "requirement": reqs[i][1] if i < len(reqs) else ""})
    counts: dict = {}
    for line in (d / "fail_to_pass.txt").read_text().splitlines():
        if line:
            k = rule_of(line) or "core"
            counts[k] = counts.get(k, 0) + 1
    st = ev["stages"]
    demo = json.loads((d / "demo_eval.json").read_text()) if (d / "demo_eval.json").exists() else None
    return {
        "id": t["task_id"], "repo": t["repo"]["name"], "family": t["family"], "title": t["title"],
        "difficulty": t["difficulty"], "base_commit": t["repo"]["base_commit"], "language": t["repo"]["language"],
        "f2p": t["fail_to_pass_count"], "p2p": t["pass_to_pass_count"], "rules": rules, "tests_by_rule": counts,
        "ref_lines": ev["ref_patch_lines"], "files": ev["files_touched"], "valid": ev["valid"], "seconds": ev["seconds"],
        "stages": {k: {kk: vv for kk, vv in v.items() if kk not in ("tail",)} for k, v in st.items()},
        "problem_md": md, "demo": demo, "dir": str(d),
    }


def build(root: Path) -> dict:
    root = Path(root)
    tasks = [_task(tj.parent) for tj in sorted(root.glob("*/*/task.json"))]
    fams = {}
    for t in tasks:
        key = f"{t['repo']}/{t['family']}"
        f = fams.setdefault(key, {"repo": t["repo"], "family": t["family"], "tasks": [], "matrix": None,
                                  "summary": getattr(ALL.get(t["repo"], {}).get(t["family"]), "summary", ""),
                                  "all_rules": [{"id": r.id, "title": r.title, "needs": list(r.needs)}
                                                for r in ALL[t["repo"]][t["family"]].ALL_RULES]
                                  if t["family"] in ALL.get(t["repo"], {}) else []})
        f["tasks"].append(t["id"])
    for m in root.glob("*/_variation_*.json"):
        j = json.loads(m.read_text()); fam = m.stem[len("_variation_"):]
        key = f"{m.parent.name}/{fam}"
        if key in fams:
            fams[key]["matrix"] = {"variants": j["variants"], "m": j["tests_i_vs_reference_j"]}
    repos = {}
    for t in tasks:
        repos.setdefault(t["repo"], {"commit": t["base_commit"], "language": t["language"]})
    return {"tasks": tasks, "families": list(fams.values()), "repos": repos}
