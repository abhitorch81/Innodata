"""TypeScript / vitest adapter (zod).

Facts about the zod test setup that shape this adapter (all verified empirically):

* `vitest run <file>` executes every test file in THREE vitest projects: the runtime project, the
  `compile-mode` project (global AOT compilation) and the **typecheck** project (tsc over the test file).
  In the JSON report the typecheck project lists the same test titles prefixed with the file path in
  `fullName`; a test "fails" there when tsc reports an error located inside the test body (e.g. an
  unused `@ts-expect-error`, a missing property).  So TYPE-level requirements are real, ablatable tests.
* A type error outside any test body (top level / imports / a broken source file) fails the *file* but
  no individual test.  We surface that as a synthetic failing id `<file>::<file-error>` so a run that
  "does not compile" is never reported green (and `build_ok` is cleared when no test ran at all).
* A test id is `<relative file>::<title>`; it passes only if it passed in every project it appears in.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

from ..core import REPOS, sh
from .base import Adapter, RunResult

NODE_BIN = "node_modules/.bin/vitest"


class VitestAdapter(Adapter):
    lang = "ts"
    feature_timeout = 240      # one test file x 3 projects ~ 10-15 s
    regression_timeout = 1800  # whole packages/zod suite

    # ------------------------------------------------------------------ workspace
    def prepare(self, ws) -> None:
        src = REPOS / ws.repo
        root = ws.root
        links = [Path("node_modules")] + [p.relative_to(src) for p in sorted(src.glob("packages/*/node_modules"))]
        for rel in links:
            dst = root / rel
            if dst.is_symlink() or dst.exists():
                continue
            if not (root / rel.parent).is_dir():
                continue
            dst.symlink_to(src / rel)
        ws_yaml = root / "pnpm-workspace.yaml"
        if not ws_yaml.exists() and (src / "pnpm-workspace.yaml").exists():
            shutil.copy(src / "pnpm-workspace.yaml", ws_yaml)
        # keep the helper file out of `git add -A` (patches must contain only the task's own changes)
        excl = Path(sh(["git", "rev-parse", "--git-path", "info/exclude"], cwd=root).stdout.strip())
        if not excl.is_absolute():
            excl = root / excl
        cur = excl.read_text() if excl.exists() else ""
        if "pnpm-workspace.yaml" not in cur:
            excl.parent.mkdir(parents=True, exist_ok=True)
            excl.write_text(cur.rstrip("\n") + "\n/pnpm-workspace.yaml\n")

    # ------------------------------------------------------------------ running vitest
    def _run(self, ws, files, timeout, exclude=()) -> RunResult:
        outdir = Path(tempfile.mkdtemp(prefix="vitest-"))
        out = outdir / "report.json"
        cmd = [NODE_BIN, "run", *files, "--reporter=json", f"--outputFile={out}"]
        for x in exclude:
            cmd.append(f"--exclude={x}")
        env = dict(os.environ, CI="1", NO_COLOR="1")
        proc = subprocess.Popen(cmd, cwd=ws.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, start_new_session=True)
        try:
            log, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:  # e.g. a mutant that loops forever: counts as detected
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            shutil.rmtree(outdir, ignore_errors=True)
            return RunResult(failed={"<timeout>"}, tail="TIMEOUT")
        try:
            return self._parse(ws, out, log)
        finally:
            shutil.rmtree(outdir, ignore_errors=True)

    def _parse(self, ws, out: Path, log: str) -> RunResult:
        r = RunResult(tail=log[-1500:])
        if not out.exists():
            r.build_ok = False
            r.failed.add("<no-report>")
            return r
        data = json.loads(out.read_text())
        root = str(ws.root) + "/"
        status: dict = {}
        file_errors: set = set()
        for f in data.get("testResults", []):
            name = f["name"].replace(root, "")
            asserts = f.get("assertionResults", [])
            if f.get("status") == "failed" and not any(a["status"] == "failed" for a in asserts):
                file_errors.add(f"{name}::<file-error>")  # import error / type error outside any test
                if not asserts:
                    r.build_ok = False
                    r.tail = (f.get("message") or "")[:1500] or r.tail
            for a in asserts:
                if a["status"] not in ("passed", "failed"):
                    continue  # skipped / todo
                title = a["fullName"]
                m = re.match(r"(\S+\.test\.ts) ", title)
                if m and name.endswith(m.group(1)):  # typecheck project prefixes the (package-relative) path
                    title = title[m.end():]
                tid = f"{name}::{title}"
                tid = re.sub(r"\s+", " ", tid)
                status.setdefault(tid, []).append(a["status"])
        for tid, st in status.items():
            (r.failed if "failed" in st else r.passed).add(tid)
        r.failed |= file_errors
        if not data.get("success", True) and not r.failed:
            r.failed.add("<unattributed-failure>")  # e.g. unhandled source errors
        if not r.passed and not r.failed:
            r.build_ok = False
            r.failed.add("<no-tests-ran>")
        return r

    # ------------------------------------------------------------------ Adapter API
    def commands(self, recipe, v):
        fp = " ".join(recipe.feature_test_paths(v))
        return {
            "setup": "pnpm install   # (repo pins `nub`; any pnpm >= 9 works with a pnpm-workspace.yaml listing packages/*)",
            "feature": f"node_modules/.bin/vitest run {fp}   # runtime + compile-mode + typecheck projects",
            "regression": "node_modules/.bin/vitest run packages/zod " + " ".join(f"--exclude={p}" for p in recipe.feature_test_paths(v)),
        }

    def run_feature(self, ws, v, recipe) -> RunResult:
        return self._run(ws, recipe.feature_test_paths(v), self.feature_timeout)

    def run_regression(self, ws, v, recipe, full=True) -> RunResult:
        excl = list(recipe.feature_test_paths(v))
        if not full and hasattr(recipe, "regression_subset"):
            files = [f for f in recipe.regression_subset(v) if f not in excl]
            r = self._run(ws, files, self.feature_timeout * 2, exclude=excl)
        else:
            r = self._run(ws, ["packages/zod"], self.regression_timeout, exclude=excl)
        r = self._retry_flaky(ws, r, excl)
        # vitest's typecheck project ignores type errors in *source* files, so compile the package
        # ourselves (tsconfig.test.json is clean on the base commit).
        for f in self._tsc(ws, excl):
            r.failed.add(f"{f}::<tsc-error>")
        return r

    def _tsc(self, ws, excl) -> set:
        try:
            p = subprocess.run(["../../node_modules/.bin/tsc", "--noEmit", "-p", "tsconfig.test.json", "--pretty", "false"],
                               cwd=ws.root / "packages/zod", capture_output=True, text=True, timeout=self.feature_timeout)
        except subprocess.TimeoutExpired:
            return {"<tsc-timeout>"}
        bad = set()
        for m in re.finditer(r"^(\S+?)\(\d+,\d+\): error", p.stdout, re.M):
            f = "packages/zod/" + m.group(1)
            if f not in excl:
                bad.add(f)
        if p.returncode and not bad and not any(e in p.stdout for e in excl):
            bad.add("<tsc-failure>")
        return bad

    def _retry_flaky(self, ws, r: RunResult, excl) -> RunResult:
        """cyclic-data.test.ts asserts on heap growth and fails under parallel load even on the pristine
        base commit.  Re-run each failing *file* once in isolation; a test that then passes is not a
        regression.  (Deterministic breakage fails twice, so this cannot mask a real regression.)"""
        files = sorted({t.split("::")[0] for t in r.failed if "::" in t})
        if not files or len(files) > 6 or r.build_ok is False:
            return r
        r2 = self._run(ws, files, self.feature_timeout * 2, exclude=excl)
        if not r2.build_ok:
            return r
        fixed = {t for t in r.failed if t in r2.passed and t not in r2.failed}
        r.failed -= fixed
        r.passed |= fixed
        return r
