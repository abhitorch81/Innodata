from __future__ import annotations
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from ..core import ROOT
from .base import Adapter, RunResult

PY = str(ROOT / ".venv" / "bin" / "python")


class PytestAdapter(Adapter):
    lang = "python"
    timeout = 120

    def _run(self, ws, args) -> RunResult:
        junit = ws.root / ".junit.xml"
        if junit.exists():
            junit.unlink()
        env = dict(os.environ, PYTHONPATH=str(ws.root / "src"), PYTHONDONTWRITEBYTECODE="1")
        try:
            p = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                f"--junitxml={junit}", *args], cwd=ws.root, env=env,
                               capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:  # e.g. a mutant that loops forever: counts as detected
            return RunResult(failed={"<timeout>"}, tail="TIMEOUT")
        r = RunResult(tail=(p.stdout + p.stderr)[-1500:])
        if not junit.exists():
            r.build_ok = False  # collection/import error that produced no report
            return r
        for tc in ET.parse(junit).getroot().iter("testcase"):
            tid = f"{tc.get('classname')}::{tc.get('name')}"
            bad = any(c.tag in ("failure", "error") for c in tc)
            (r.failed if bad else r.passed).add(tid)
        if "error" in p.stdout.lower() and "ERROR collecting" in p.stdout:
            r.build_ok = False
        return r

    def commands(self, recipe, v):
        return {"setup": "python -m venv .venv && .venv/bin/pip install -e . pytest",
                "feature": "PYTHONPATH=src pytest " + " ".join(recipe.feature_test_paths(v)),
                "regression": "PYTHONPATH=src pytest tests " + " ".join(f"--ignore={p}" for p in recipe.feature_test_paths(v))}

    def prepare(self, ws):
        pass

    def run_feature(self, ws, v, recipe):
        return self._run(ws, recipe.feature_test_paths(v))

    def run_regression(self, ws, v, recipe, full=True):
        ign = [f"--ignore={x}" for x in recipe.feature_test_paths(v)]
        args = ["tests", *ign]
        if not full and getattr(recipe, "regression_subset", None):
            args = [*recipe.regression_subset(v), *ign]
        return self._run(ws, args)
