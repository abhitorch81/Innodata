"""C++ adapter: builds jsoncpp's own test binary with g++ (no cmake) and parses its report.

Speed: every translation unit is compiled to an object file cached by a content hash of the
source + all headers, so a mutant that touches one .cpp only recompiles what changed (and units
are compiled in parallel). The binary lives outside the worktree.

Semantics required by validate.py
  * compile/link failure         -> RunResult(build_ok=False, tail="COMPILE...")
  * one build + one run per tree -> results split by test-name prefix `Task` (task fixtures are
    "feature", everything else is "regression")
  * every run has a timeout; a hang/crash reports failed={"<timeout>"} / missing tests as failed.
"""
from __future__ import annotations
import hashlib
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..core import SCRATCH
from .base import Adapter, RunResult

PREFIX = "Task"  # task fixtures are named Task<Something>Test
CXXFLAGS = ["-std=c++11", "-O0", "-Iinclude", "-DJSON_USE_EXCEPTION=1"]
SOURCES = ["src/lib_json/json_reader.cpp", "src/lib_json/json_value.cpp", "src/lib_json/json_writer.cpp",
           "src/test_lib_json/fuzz.cpp", "src/test_lib_json/jsontest.cpp", "src/test_lib_json/main.cpp"]
CACHE = SCRATCH / "jsoncpp-obj-cache"
LINE = re.compile(r"^Testing (\S+): (OK|FAILED)\s*$", re.M)


class GppAdapter(Adapter):
    lang = "cpp"
    compile_timeout = 180
    run_timeout = 12

    def __init__(self):
        self.bin = SCRATCH / f"jsoncpp-bin-{os.getpid()}"
        self._last = (None, None)  # (tree key, all results)

    # ------------------------------------------------------------------ build
    def _key(self, root: Path):
        hdr = hashlib.sha1()
        for p in sorted(list((root / "include").rglob("*.h")) + list((root / "src").rglob("*.h"))
                        + list((root / "src").rglob("*.inl"))):
            hdr.update(p.read_bytes())
        keys = {}
        for s in SOURCES:
            keys[s] = hashlib.sha1(hdr.digest() + (root / s).read_bytes() + " ".join(CXXFLAGS).encode()).hexdigest()
        return keys

    def _compile(self, root: Path, src: str, key: str):
        obj = CACHE / f"{key}.o"
        if obj.exists():
            return obj, ""
        tmp = CACHE / f"{key}.{os.getpid()}.tmp.o"
        p = subprocess.run(["g++", *CXXFLAGS, "-c", src, "-o", str(tmp)], cwd=root,
                           capture_output=True, text=True, timeout=self.compile_timeout)
        if p.returncode:
            return None, (p.stderr or p.stdout)
        os.replace(tmp, obj)
        return obj, ""

    def _build(self, ws):
        """-> (tree_key, error_tail)"""
        CACHE.mkdir(parents=True, exist_ok=True)
        root = ws.root
        keys = self._key(root)
        tree = hashlib.sha1("".join(keys[s] for s in SOURCES).encode()).hexdigest()
        try:
            with ThreadPoolExecutor(len(SOURCES)) as ex:
                res = list(ex.map(lambda s: self._compile(root, s, keys[s]), SOURCES))
        except subprocess.TimeoutExpired:
            return None, "COMPILE timeout"
        errs = [e for o, e in res if o is None]
        if errs:
            return None, "COMPILE error\n" + errs[0][-1500:]
        p = subprocess.run(["g++", *[str(o) for o, _ in res], "-o", str(self.bin)],
                           capture_output=True, text=True, timeout=self.compile_timeout)
        if p.returncode:
            return None, "COMPILE link error\n" + (p.stderr or p.stdout)[-1500:]
        return tree, ""

    # ------------------------------------------------------------------ run
    def _exec(self, args):
        return subprocess.run([str(self.bin), "--test-auto", *args], capture_output=True, text=True,
                              timeout=self.run_timeout, errors="replace")

    def _run_all(self, ws, names=None):
        """Build once, run once; -> (ok, passed, failed, tail) over ALL tests (cached per tree)."""
        tree, err = self._build(ws)
        if tree is None:
            return None, err
        ck = (tree, tuple(names or ()))
        if self._last[0] == ck:
            return self._last[1], ""
        args = [a for n in (names or ()) for a in ("--test", n)]
        try:
            p = self._exec(args)
        except subprocess.TimeoutExpired:
            out = ("timeout", None)
            self._last = (ck, out)
            return out, ""
        text = p.stdout + p.stderr
        passed, failed = set(), set()
        for name, st in LINE.findall(p.stdout):
            (passed if st == "OK" else failed).add(name)
        complete = bool(re.search(r"^(All \d+ tests passed|\d+/\d+ tests passed)", p.stdout, re.M)) or \
            (names is not None and len(names) == 1 and p.returncode in (0, 1))
        if not complete:  # crashed mid-run: every test that never reported counts as failed
            try:
                listed = set(subprocess.run([str(self.bin), "--list-tests"], capture_output=True, text=True,
                                            timeout=30).stdout.split())
            except subprocess.TimeoutExpired:
                listed = set()
            failed |= {n for n in (listed if not names else set(names)) if n not in passed and n not in failed}
            failed.add("<crash rc=%s>" % p.returncode)
        out = ("done", (passed, failed, text[-1500:]))
        self._last = (ck, out)
        return out, ""

    def _split(self, ws, names, want_task):
        out, err = self._run_all(ws, names)
        if out is None:
            return RunResult(build_ok=False, tail=err)
        if out[0] == "timeout":
            return RunResult(failed={"<timeout>"}, tail="TIMEOUT")
        passed, failed, tail = out[1]
        sel = (lambda n: n.startswith(PREFIX)) if want_task else (lambda n: not n.startswith(PREFIX))
        r = RunResult(passed={n for n in passed if sel(n)},
                      failed={n for n in failed if sel(n) or n.startswith("<")}, tail=tail)
        return r

    # ------------------------------------------------------------------ Adapter API
    def commands(self, recipe, v):
        build = ("g++ -std=c++11 -O0 -Iinclude -DJSON_USE_EXCEPTION=1 src/lib_json/*.cpp "
                 "src/test_lib_json/*.cpp -o jsoncpp_tests")
        return {"setup": "none (only a C++11 compiler is needed)", "build": build,
                "feature": "./jsoncpp_tests --test-auto   # lines `Testing Task*/...: OK|FAILED`",
                "regression": "./jsoncpp_tests --test-auto   # every non-`Task*` line must be OK"}

    def prepare(self, ws):
        pass

    def run_feature(self, ws, v, recipe):
        return self._split(ws, None, True)

    def run_regression(self, ws, v, recipe, full=True):
        names = None
        if not full and v is not None and getattr(recipe, "regression_subset", None):
            names = list(recipe.regression_subset(v)) or None
        return self._split(ws, names, False)
