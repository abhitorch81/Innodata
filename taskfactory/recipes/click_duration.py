"""click / Duration: a new ParamType parsing human durations into ``datetime.timedelta``.

Rule algebra: units(param) x {compound, ordered, bare, fraction, case, negative, spaces, bounds}.
Implementation text is *generated from the rule set*; expected test values come from an independent
oracle (`model`) that is a hand-written character scanner (the implementation uses regexes)."""
from __future__ import annotations
import random
from decimal import Decimal, ROUND_HALF_EVEN
from ..core import Recipe, Rule, Variant, Edit

UNIT_SECONDS = {"ms": "0.001", "s": "1", "m": "60", "h": "3600", "d": "86400", "w": "604800"}
UNIT_NAME = {"ms": "milliseconds", "s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
ORDER = ["w", "d", "h", "m", "s", "ms"]


class ClickDuration(Recipe):
    repo = "click"
    family = "duration"
    summary = "New `click.Duration` parameter type (human duration strings -> timedelta)"
    CORE = ("core",)
    ALL_RULES = [
        Rule("core", "Basic type",
             "Add a new parameter type `click.Duration` (defined in `click/types.py`, exported from the top-level "
             "`click` package) that converts a command-line string into a `datetime.timedelta`. Its `name` is "
             "`\"duration\"`. A valid value is a non-negative integer written with ASCII digits `0-9`, immediately "
             "followed by a unit suffix, with no whitespace anywhere. Supported units (lowercase only): {unit_desc}. "
             "The result is the number multiplied by the unit's length. A `timedelta` passed to `convert` is "
             "returned unchanged. Any other input - including the empty string, unknown units, non-ASCII digits, "
             "and values too large for `timedelta` to represent - must fail by calling `self.fail(...)` (so users "
             "get the standard `BadParameter`, exit code 2) with a message that contains `repr()` of the "
             "offending input."),
        Rule("compound", "Compound values",
             "A value may consist of two or more number+unit segments written back to back, e.g. `1h30m`; its "
             "value is the sum of the segments. Every segment must carry its own unit and obeys all other rules "
             "(a segment like `30` without a unit makes the whole value invalid)."),
        Rule("ordered", "Segment order", "In a compound value the segments must go from the largest unit to the "
             "smallest and each unit may appear at most once: `1h30m` is valid; `30m1h` and `1m1m` are not.",
             needs=("compound",)),
        Rule("bare", "Bare numbers", "A bare number with no unit (e.g. `90`) is accepted and means that many "
             "seconds. This is accepted only when the bare number is the entire input, never as a segment of a "
             "compound value."),
        Rule("fraction", "Fractional numbers", "The number in a segment (and a bare number) may have a fractional "
             "part: ASCII digits, a `.`, then ASCII digits (so `1.5h` and `0.25m` are valid, `.5s` and `5.s` are not). "
             "Arithmetic must be exact decimal arithmetic (not binary floating point), with the final total "
             "rounded half-even to the nearest microsecond."),
        Rule("case", "Case-insensitive units", "Unit suffixes are matched case-insensitively: `5M`, `1H30m`, "
             "`2MS` are valid (when the lowercase unit is supported). The suffix is matched as a whole."),
        Rule("negative", "Negative values", "A value may begin with a single `-`, which negates the whole value "
             "(every segment of a compound value): `-90s`, `-1h30m`. A `-` anywhere else is invalid, and `-` "
             "must be directly followed by the number (no whitespace between them)."),
        Rule("spaces", "Whitespace tolerance", "Spaces and tab characters are tolerated: leading/trailing "
             "whitespace is ignored, and whitespace is allowed between a number and its unit (`5 m`) and between "
             "segments (`1h 30m`). Whitespace inside a number is still invalid, and an input of only whitespace "
             "is invalid."),
        Rule("bounds", "Optional bounds", "`Duration(min=None, max=None)` accepts optional inclusive `timedelta` "
             "bounds (`min={min_s}` seconds and `max={max_s}` seconds are used in tests). A converted value outside the "
             "bounds - including a `timedelta` passed straight to `convert` - fails exactly like any other "
             "invalid input (message contains `repr()` of the input). Without the arguments there are no bounds."),
    ]

    # ------------------------------------------------------------------ sampling
    def sample_params(self, rng, rules):
        extra = rng.sample(["ms", "d", "w"], rng.randint(1, 3))
        units = ["s", "m", "h"] + extra
        units.sort(key=ORDER.index)
        return {"units": units,
                "unit_desc": ", ".join(f"`{u}` ({UNIT_NAME[u]}, {UNIT_SECONDS[u]} s)" for u in units),
                "min_s": rng.choice([30, 60, 300]), "max_s": rng.choice([3600, 7200, 86400])}

    def title(self, v): return "Add a `Duration` parameter type"
    def preamble(self, v):
        return ("Click can parse integers, floats, dates and paths from the command line, but not durations "
                "such as `90s` or `1h30m`. Implement the type described below, following the conventions of "
                "the existing parameter types in `click/types.py`.")

    # ------------------------------------------------------------------ oracle
    def model(self, text, R, P):
        """Independent character-scanner oracle. Returns microseconds (int) or None if invalid."""
        U = {u: Decimal(UNIT_SECONDS[u]) for u in P["units"]}
        s = text
        if "spaces" in R:
            s = s.strip(" \t")
        neg = False
        if "negative" in R and s.startswith("-"):
            neg, s = True, s[1:]
        if not s:
            return None
        digs = "0123456789"
        i, total, prev, n_seg = 0, Decimal(0), None, 0
        while i < len(s):
            j = i
            while j < len(s) and s[j] in digs:
                j += 1
            if j == i:
                return None
            if "fraction" in R and j < len(s) and s[j] == "." and j + 1 < len(s) and s[j + 1] in digs:
                j += 1
                while j < len(s) and s[j] in digs:
                    j += 1
            num = Decimal(s[i:j])
            k = j
            if "spaces" in R:
                while k < len(s) and s[k] in " \t":
                    k += 1
            e = k
            while e < len(s) and s[e].isascii() and s[e].isalpha():
                e += 1
            unit = s[k:e]
            if unit == "":
                if k != len(s) or n_seg or j != len(s) and False:
                    return None
                # bare number: only legal as whole input
                if "bare" in R and i == 0 and j == len(s):
                    total = num
                    n_seg = 1
                    i = len(s)
                    break
                return None
            key = unit.lower() if "case" in R else unit
            if key not in U:
                return None
            if prev is not None and "ordered" in R and not U[key] < prev:
                return None
            prev = U[key]
            total += num * U[key]
            n_seg += 1
            i = e
            if i < len(s) and "spaces" in R:
                while i < len(s) and s[i] in " \t":
                    i += 1
            if n_seg > 1 and "compound" not in R:
                return None
            if i < len(s) and "compound" not in R:
                return None
        if n_seg == 0:
            return None
        us = int((total * 1000000).to_integral_value(rounding=ROUND_HALF_EVEN))
        if neg:
            us = -us
        if abs(us) > 999999999 * 86400 * 10 ** 6 + 86399999999:
            return None  # beyond datetime.timedelta
        if "bounds" in R and not (P["min_s"] * 10 ** 6 <= us <= P["max_s"] * 10 ** 6):
            return None
        return us

    # ------------------------------------------------------------------ implementation
    def impl_edits(self, v, rules):
        P = v.params
        units = {u: UNIT_SECONDS[u] for u in P["units"]}
        has = rules.__contains__
        num = "[0-9]+(?:\\.[0-9]+)?" if has("fraction") else "[0-9]+"
        ws = "[ \\t]*" if has("spaces") else ""
        unit_lines = "\n".join(f'        "{u}": "{s}",' for u, s in units.items())
        init = ""
        if has("bounds"):
            init = ("    def __init__(\n        self, min: timedelta | None = None, max: timedelta | None = None\n    ) -> None:\n"
                    "        self.min = min\n        self.max = max\n\n")
        cls = f'''class Duration(ParamType[timedelta]):
    """Convert strings such as ``90s`` or ``1h30m`` into :class:`~datetime.timedelta`.

    A value is a number followed by a unit suffix.
    """

    name = "duration"

    _UNITS: t.ClassVar[dict[str, str]] = {{
{unit_lines}
    }}
    _NUMBER = re.compile(r"{num}")
    _SEGMENT = re.compile(r"(?P<number>{num}){ws}(?P<unit>[A-Za-z]+)")

{init}'''
        cls += self._convert_src(rules)
        cls += "\n    def __repr__(self) -> str:\n        return \"DURATION\"\n\n\n"
        return [
            Edit("src/click/types.py", "replace", "from datetime import datetime\nfrom datetime import timedelta\n",
                 anchor="from datetime import datetime\n"),
            Edit("src/click/types.py", "replace", "import enum\nimport os\nimport re\n", anchor="import enum\nimport os\n"),
            Edit("src/click/types.py", "insert_before", cls, anchor="class _NumberParamTypeBase("),
            Edit("src/click/__init__.py", "insert_after", "from .types import Duration as Duration\n",
                 anchor="from .types import DateTime as DateTime\n"),
        ]

    def _convert_src(self, rules):
        has = rules.__contains__
        L = []
        a = L.append
        a("    def convert(\n        self, value: t.Any, param: Parameter | None, ctx: Context | None\n    ) -> timedelta:")
        a("        if isinstance(value, timedelta):\n            result = value\n        else:\n            result = self._parse(value)\n")
        a("            if result is None:\n                self.fail(_(\"{value!r} is not a valid duration.\").format(value=value), param, ctx)\n")
        if has("bounds"):
            a("        if (self.min is not None and result < self.min) or (\n            self.max is not None and result > self.max\n        ):")
            a("            self.fail(_(\"{value!r} is outside the allowed duration range.\").format(value=value), param, ctx)\n")
        a("        return result\n")
        # parser
        a("    def _parse(self, value: t.Any) -> timedelta | None:")
        a("        from decimal import Decimal  # lazy: keeps `import click` light\n")
        a("        if not isinstance(value, str):\n            return None\n")
        a("        text = value")
        if has("spaces"):
            a("        text = text.strip(\" \\t\")")
        a("        sign = 1")
        if has("negative"):
            a("        if text.startswith(\"-\"):\n            sign = -1\n            text = text[1:]")
        a("        if not text:\n            return None\n")
        if has("bare"):
            a("        if self._NUMBER.fullmatch(text):\n            total = Decimal(text)\n            return self._build(total, sign)\n")
        a("        total = Decimal(0)\n        pos = 0\n        count = 0")
        if has("ordered"):
            a("        previous = None")
        a("        while pos < len(text):\n            m = self._SEGMENT.match(text, pos)\n            if m is None:\n                return None\n")
        a("            unit = m.group(\"unit\")" + (".lower()" if has("case") else ""))
        a("            spec = self._UNITS.get(unit)\n            if spec is None:\n                return None\n            factor = Decimal(spec)")
        if has("ordered"):
            a("            if previous is not None and factor >= previous:\n                return None\n            previous = factor")
        a("            total += Decimal(m.group(\"number\")) * factor\n            count += 1\n            pos = m.end()")
        if has("spaces"):
            a("            while pos < len(text) and text[pos] in \" \\t\":\n                pos += 1")
        if has("compound"):
            pass
        else:
            a("            if pos != len(text):\n                return None")
        a("\n        return self._build(total, sign)\n")
        a("    @staticmethod\n    def _build(total: t.Any, sign: int) -> timedelta | None:")
        a("        micros = int((total * 1_000_000).to_integral_value())")
        a("        try:\n            return timedelta(microseconds=sign * micros)\n        except OverflowError:\n            return None")
        return "\n".join(L) + "\n"

    # ------------------------------------------------------------------ tests
    def feature_test_paths(self, v):
        return ["tests/test_task_duration.py"]

    POOLS = {
        "core": ["30s", "5m", "2h", "0s", "007s", "1d", "2w", "250ms", "", "abc", "5x", "m", "s5", "5", "1.5s",
                 "-5s", " 5s", "5s ", "5 s", "1h30m", "٣s", "5S", "5mm", "9999999999999d", "999999999d", "+5s", "5s5"],
        "compound": ["1h30m", "90m30s", "1m1m", "30m1h", "1h30", "1h 30m", "1h30m15s", "2d12h", "1h-30m", "1s2ms", "1h30m1x"],
        "ordered": ["1h30m", "30m1h", "1m1m", "1s1m", "1h1h", "1d1h1m", "1m2h"],
        "bare": ["90", "0", "007", "1h30", "30 ", "9 0", "1.5", "-5", "1m30"],
        "fraction": ["1.5h", "0.25m", "1.5", ".5s", "5.s", "1.5.5s", "0.001s", "1.0000005s", "2.5s", "1.2.3h"],
        "case": ["5M", "1H30m", "2MS", "5S", "5mS", "5Ms", "1D", "2W", "5Min"],
        "negative": ["-90s", "-1h30m", "--5s", "1h-30m", "-", "-0s", "- 5s", "-5", "5-"],
        "spaces": [" 5s", "5s ", "5 s", "1h 30m", "\t5m\t", " ", "1 5s", "5 s 3 m", "- 5s", "1h  30m", "5\ns", "1.5 h"],
        "bounds": [],
    }

    def test_edits(self, v):
        P, R = v.params, set(v.rules)
        pool = dict(self.POOLS)
        b = [f"{P['min_s'] - 1}s", f"{P['min_s']}s", f"{P['max_s']}s", f"{P['max_s'] + 1}s", "0s", "1s",
             f"{P['max_s'] // 60}m", f"{P['max_s'] // 60 + 1}m"]
        if "negative" in R: b += [f"-{P['min_s']}s"]
        if "compound" in R: b += [f"{P['max_s'] // 3600}h1s"]
        pool["bounds"] = b
        sections = []
        for rid in v.rules:
            drop = {rid} | {x for x in v.rules if rid in self.rule(x).needs}
            Reff = R if rid == "bounds" else R - {"bounds"}  # only bounds tests construct a bounded type
            full, abl = Reff, Reff - drop
            cands = pool.get(rid, [])
            disc, same = [], []
            for c in cands:
                m1 = self.model(c, full, P)
                m0 = self.model(c, abl, P) if rid != "core" else (None if m1 is not None else m1)
                (disc if m1 != m0 else same).append((c, m1))
            if rid == "core":
                # core cases must hold for EVERY variant: keep only those whose outcome does not depend on
                # any optional rule (model with all rules == model with the core rules only).
                only = {"core"}
                same = [(c, self.model(c, full, P)) for c in cands if self.model(c, full, P) == self.model(c, only, P)]
                chosen = same
            else:
                if not disc:
                    raise RuntimeError(f"rule {rid}: no discriminating case in pool for variant {v.id}")
                keep_same = [x for x in same if x[1] is not None][:2] + [x for x in same if x[1] is None][:1]
                chosen = disc + keep_same
            sections.append((rid, chosen))
        # ---- render
        lines = ['"""Hidden tests for the Duration task (generated; one `rule_<id>` test per requirement)."""',
                 "import datetime as dt", "", "import click", "import pytest", "from click.testing import CliRunner", "",
                 "US = dt.timedelta(microseconds=1)", "",
                 "", "def _run(text, **kw):",
                 "    @click.command()", "    @click.option(\"--t\", type=click.Duration(**kw))",
                 "    def cli(t):", "        click.echo(str(t // US))", "",
                 "    return CliRunner().invoke(cli, [\"--t=\" + text])", "", "",
                 "def _check(text, expected, **kw):", "    res = _run(text, **kw)",
                 "    if expected is None:",
                 "        assert res.exit_code == 2, f\"{text!r} should be rejected, got {res.output!r}\"",
                 "        assert repr(text) in res.output, res.output",
                 "    else:",
                 "        assert res.exit_code == 0, f\"{text!r} should parse: {res.output!r}\"",
                 "        assert res.output.strip() == str(expected), f\"{text!r}: {res.output!r}\"", "", ""]
        kw = f"min=dt.timedelta(seconds={P['min_s']}), max=dt.timedelta(seconds={P['max_s']})"
        for rid, chosen in sections:
            cases = ",\n    ".join(f"({c!r}, {e!r})" for c, e in chosen)
            call = f"_check(text, expected, {kw})" if rid == "bounds" else "_check(text, expected)"
            lines += [f"CASES_{rid.upper()} = [\n    {cases},\n]", "",
                      f"@pytest.mark.parametrize(\"text,expected\", CASES_{rid.upper()}, ids=[f\"c{{i}}\" for i in range(len(CASES_{rid.upper()}))])",
                      f"def test_rule_{rid}(text, expected):", f"    {call}", "", ""]
        lines += ["def test_rule_core_api():",
                  "    assert click.types.Duration is click.Duration",
                  "    assert click.Duration().name == \"duration\"",
                  "    td = dt.timedelta(hours=1, seconds=7)",
                  "    assert click.Duration().convert(td, None, None) == td", ""]
        if "bounds" in R:
            lines += ["def test_rule_bounds_timedelta_passthrough():",
                      f"    typ = click.Duration({kw})",
                      f"    assert typ.convert(dt.timedelta(seconds={P['min_s']}), None, None) == dt.timedelta(seconds={P['min_s']})",
                      "    with pytest.raises(click.BadParameter):",
                      f"        typ.convert(dt.timedelta(seconds={P['max_s'] + 1}), None, None)", ""]
        return [Edit("tests/test_task_duration.py", "create", "\n".join(lines) + "\n", role="test")]

