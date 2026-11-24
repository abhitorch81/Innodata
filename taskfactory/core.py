"""Core data model + workspace handling shared by every repo / language.

Design rule: a task is *data*  (a Variant = family + sampled rule set + params).
Everything else - requirements text, reference patch, feature tests, ablated
(wrong) implementations, mutants - is *derived* from that one object, so the
requirements, the implementation and the tests cannot drift apart.
"""
from __future__ import annotations

import dataclasses as dc
import os
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
REPOS = ROOT / "repos"
SCRATCH = ROOT / ".scratch"


# --------------------------------------------------------------------------- edits
@dc.dataclass
class Edit:
    """A deterministic, anchor-based source edit (fails loudly if the repo drifts)."""

    path: str
    kind: str  # create | append | insert_after | insert_before | replace | replace_line
    text: str = ""
    anchor: str = ""
    role: str = "impl"  # impl | test

    def apply(self, root: Path) -> None:
        p = root / self.path
        if self.kind == "create":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(self.text)
            return
        src = p.read_text()
        if self.kind == "append":
            out = src.rstrip("\n") + "\n" + self.text
        else:
            n = src.count(self.anchor)
            if n != 1:
                raise AnchorError(f"{self.path}: anchor {self.anchor[:60]!r} matched {n}x")
            i = src.index(self.anchor)
            j = i + len(self.anchor)
            if self.kind == "insert_after":
                out = src[:j] + self.text + src[j:]
            elif self.kind == "insert_before":
                out = src[:i] + self.text + src[i:]
            elif self.kind in ("replace", "replace_line"):
                out = src[:i] + self.text + src[j:]
            else:
                raise ValueError(self.kind)
        p.write_text(out)


class AnchorError(Exception):
    pass


# --------------------------------------------------------------------------- spec
@dc.dataclass
class Rule:
    id: str  # alphanumeric only: it is embedded in test names for attribution
    title: str
    requirement: str  # agent-facing sentence(s); the ONLY source of truth for the rule
    needs: tuple = ()  # rules that must also be enabled


@dc.dataclass
class Variant:
    family: str
    seed: int
    rules: list  # enabled rule ids, in canonical order
    params: dict = dc.field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.family}-{self.seed:02d}"


class Recipe:
    """One *family* of features for one repository. Subclasses supply the three
    derivations (requirements / implementation / tests); the framework supplies
    sampling, validation, ablation, mutation and packaging."""

    repo: str = ""
    family: str = ""
    summary: str = ""
    ALL_RULES: list = []  # list[Rule]; first entries flagged in CORE are always on
    CORE: tuple = ()
    feature_test_paths: Callable = None  # (variant) -> [relative paths]

    def rule(self, rid: str) -> Rule:
        return next(r for r in self.ALL_RULES if r.id == rid)

    # -- sampling: seeded, deterministic, guarantees pairwise-distinct rule sets
    def sample(self, n: int, seed: int = 0) -> list:
        rng = random.Random(seed)
        optional = [r for r in self.ALL_RULES if r.id not in self.CORE]
        seen, out, tries = set(), [], 0
        while len(out) < n and tries < 500:
            tries += 1
            k = rng.randint(max(2, len(optional) // 3), max(2, len(optional) - 1))
            pick = set(rng.sample([r.id for r in optional], min(k, len(optional))))
            changed = True
            while changed:  # close under `needs`
                changed = False
                for r in optional:
                    if r.id in pick:
                        for d in r.needs:
                            if d not in pick and d not in self.CORE:
                                pick.add(d); changed = True
            key = frozenset(pick)
            if key in seen:
                continue
            seen.add(key)
            rules = [r.id for r in self.ALL_RULES if r.id in self.CORE or r.id in pick]
            out.append(Variant(self.family, len(out) + 1, rules, self.sample_params(rng, rules)))
        return out

    def sample_params(self, rng, rules) -> dict:
        return {}

    # -- derivations (override)
    def title(self, v: Variant) -> str: raise NotImplementedError
    def preamble(self, v: Variant) -> str: raise NotImplementedError
    def impl_edits(self, v: Variant, rules: set) -> list: raise NotImplementedError
    def test_edits(self, v: Variant) -> list: raise NotImplementedError

    def requirements_md(self, v: Variant) -> str:
        lines = [f"# {self.title(v)}", "", self.preamble(v), "", "## Requirements", ""]
        for i, rid in enumerate(v.rules, 1):
            r = self.rule(rid)
            lines.append(f"{i}. **{r.title}.** {r.requirement.format(**v.params)}")
        lines += ["", "## Notes", "",
                  "- Do not modify existing tests. Hidden tests cover every numbered requirement above "
                  "and the repository's existing test-suite must keep passing.",
                  "- Anything not stated above is unspecified and is not tested."]
        return "\n".join(lines) + "\n"

    def ablation_sets(self, v: Variant) -> dict:
        """rule id -> rule set with that rule (and anything depending on it) removed."""
        out = {}
        for rid in v.rules:
            if rid in self.CORE:
                continue
            drop = {rid}
            grew = True
            while grew:
                grew = False
                for x in v.rules:
                    if x not in drop and any(d in drop for d in self.rule(x).needs):
                        drop.add(x); grew = True
            out[rid] = (set(v.rules) - drop, drop)
        return out


# --------------------------------------------------------------------------- workspace
def sh(cmd, cwd=None, env=None, timeout=900, check=True):
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"{cmd} failed:\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return p


class Workspace:
    """A scratch git worktree pinned to the task's base commit."""

    def __init__(self, repo: str, name: str | None = None):
        self.repo = repo
        self.src = REPOS / repo
        self.base = sh(["git", "rev-parse", "HEAD"], cwd=self.src).stdout.strip()
        self.root = SCRATCH / (name or f"{repo}-ws")

    def reset(self) -> Path:
        if not self.root.exists():
            SCRATCH.mkdir(exist_ok=True)
            sh(["git", "worktree", "add", "--detach", "-f", str(self.root), self.base], cwd=self.src)
        else:
            sh(["git", "reset", "--hard", "-q", self.base], cwd=self.root)
            sh(["git", "clean", "-fdq"], cwd=self.root)
        return self.root

    def apply(self, edits) -> None:
        for e in edits:
            e.apply(self.root)

    def apply_patch(self, patch: str) -> None:
        if not patch.strip():
            return
        p = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=self.root,
                           input=patch, text=True, capture_output=True)
        if p.returncode:
            raise RuntimeError("patch does not apply to base commit:\n" + p.stderr)

    def diff(self) -> str:
        sh(["git", "add", "-A"], cwd=self.root)
        d = sh(["git", "diff", "--cached", "--no-color", self.base], cwd=self.root).stdout
        sh(["git", "reset", "-q"], cwd=self.root)
        return d
