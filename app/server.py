"""Live backend for the Task Factory app (stdlib only).

  GET  /api/health            -> {"live": true}
  GET  /api/data              -> packaged tasks (same shape as the static data.js)
  GET  /api/live              -> tasks generated live from the app (app/live_out)
  POST /api/evaluate          {task, candidate}  -> real grader result (candidate: reference|empty|tamper|ablate:<rule>)
  POST /api/build             {repo, family, seed, n, mutants, rules}  -> text/event-stream of the real build log
Run:  .venv/bin/python app/server.py [port]
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from taskfactory.appdata import build as build_data  # noqa: E402
from taskfactory.adapters import get_adapter  # noqa: E402
from taskfactory.demo import candidate_patch  # noqa: E402
from taskfactory.factory import evaluate  # noqa: E402

LIVE_OUT = APP / "live_out"
LOCKS: dict = {}
DATA_CACHE: dict = {}


def lock_for(repo: str) -> threading.Lock:
    return LOCKS.setdefault(repo, threading.Lock())  # one job per repo: they share a scratch worktree


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(APP), **k)

    def log_message(self, fmt, *args):  # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            return self._json({"live": True, "time": time.time()})
        if self.path == "/api/data":
            return self._json(build_data(ROOT / "tasks"))
        if self.path == "/api/live":
            return self._json(build_data(LIVE_OUT) if LIVE_OUT.exists() else {"tasks": [], "families": [], "repos": {}})
        return super().do_GET()

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self):
        try:
            b = self._body()
            if self.path == "/api/evaluate":
                return self._evaluate(b)
            if self.path == "/api/build":
                return self._build(b)
            self._json({"error": "unknown endpoint"}, 404)
        except Exception as e:  # surface errors to the UI instead of hanging
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _task_dir(self, tid: str) -> Path:
        for base in (ROOT / "tasks", LIVE_OUT):
            d = base / tid
            if (d / "task.json").exists():
                return d
        raise FileNotFoundError(tid)

    def _evaluate(self, b):
        td = self._task_dir(b["task"])
        repo = td.parent.name
        lang = json.loads((td / "task.json").read_text())["repo"]["language"]
        lk = lock_for(repo)
        if not lk.acquire(blocking=False):
            return self._json({"error": f"{repo} workspace is busy with another job"}, 409)
        try:
            t0 = time.time()
            res = evaluate(td, candidate_patch(td, b["candidate"]), get_adapter(lang))
            res["seconds"] = round(time.time() - t0, 1)
            self._json(res)
        finally:
            lk.release()

    def _build(self, b):
        repo, fam = b["repo"], b["family"]
        lk = lock_for(repo)
        if not lk.acquire(blocking=False):
            return self._json({"error": f"{repo} workspace is busy with another job"}, 409)
        try:
            cmd = [str(ROOT / ".venv/bin/python"), "-u", "-m", "taskfactory", "build", "--repo", repo, "--family", fam,
                   "-n", str(int(b.get("n", 1))), "--seed", str(int(b.get("seed", 1))),
                   "--mutants", str(int(b.get("mutants", 8))), "--no-matrix"]
            if b.get("rules"):
                cmd += ["--rules", ",".join(b["rules"])]
            env = dict(os.environ, TASKFACTORY_OUT=str(LIVE_OUT))
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache"); self.end_headers()
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                self.wfile.write(f"data: {json.dumps({'line': line.rstrip()})}\n\n".encode()); self.wfile.flush()
            p.wait()
            self.wfile.write(f"data: {json.dumps({'done': True, 'code': p.returncode})}\n\n".encode()); self.wfile.flush()
        finally:
            lk.release()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Task Factory live app: http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
