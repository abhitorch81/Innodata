"""Candidate-solution generators used by the demo script and the live app."""
from __future__ import annotations
import json
import re
from pathlib import Path

from .core import Variant, Workspace
from .recipes import ALL


def candidate_patch(td: Path, kind: str) -> str:
    """kind: reference | empty | tamper | ablate:<rule>  (a plausible solution that forgets one requirement)."""
    td = Path(td)
    t = json.loads((td / "task.json").read_text()); vj = json.loads((td / "variant.json").read_text())
    recipe = ALL[t["repo"]["name"]][vj["family"]]
    v = Variant(vj["family"], vj["seed"], vj["rules"], vj["params"])
    if kind == "reference":
        return (td / "reference.patch").read_text()
    if kind == "empty":
        return ""
    if kind == "tamper":
        first = re.findall(r"^diff --git a/(\S+)", (td / "tests.patch").read_text(), re.M)[0]
        return f"diff --git a/{first} b/{first}\n--- a/{first}\n+++ b/{first}\n@@ -0,0 +1 @@\n+x\n"
    if kind.startswith("ablate:"):
        rid = kind.split(":", 1)[1]
        rules, _ = recipe.ablation_sets(v)[rid]
        ws = Workspace(t["repo"]["name"]); ws.reset()
        ws.apply(recipe.impl_edits(v, set(rules)))
        return ws.diff()
    raise ValueError(kind)
