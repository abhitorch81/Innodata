from __future__ import annotations
import dataclasses as dc
import re


@dc.dataclass
class RunResult:
    build_ok: bool = True
    passed: set = dc.field(default_factory=set)
    failed: set = dc.field(default_factory=set)
    tail: str = ""

    @property
    def total(self): return len(self.passed) + len(self.failed)
    @property
    def ok(self): return self.build_ok and not self.failed and bool(self.passed)


def rule_of(test_id: str):
    m = re.search(r"rule_?([A-Za-z0-9]+?)(?:__|_|\b|$)", test_id)
    return m.group(1) if m else None


class Adapter:
    lang = ""
    def prepare(self, ws) -> None: ...
    def run_feature(self, ws, v, recipe) -> RunResult: raise NotImplementedError
    def run_regression(self, ws, v, recipe, full=True) -> RunResult: raise NotImplementedError
