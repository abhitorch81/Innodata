"""click / option relations: `conflicts_with`, `requires`, exclusive groups on ``click.Option``.

Unlike click_duration (purely additive), this family edits EXISTING code paths
(Option.__init__, Command.parse_args, Option.get_help_record) so the regression-guard stage is meaningful.
Test scenarios are sampled randomly from the option grammar; the independent oracle `model` decides expected
outcomes and the ablation machinery selects the scenarios that discriminate each rule."""
from __future__ import annotations
import random
from ..core import Recipe, Rule, Variant, Edit

# fixed command layout (order = declaration order). kind: str | int | flag
OPTS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
GROUP = {"foxtrot", "golf", "hotel"}
VALUE = {"alpha": ["x"], "bravo": ["y"], "charlie": ["3", "0"], "delta": ["d", ""], "foxtrot": ["f"], "golf": ["2", "0"]}
FLAGS = {"echo": ["--echo", "--no-echo"], "hotel": ["--hotel", "--no-hotel"]}
CONFLICTS = {"alpha": ["bravo", "ghost"], "bravo": ["alpha"], "charlie": ["echo"]}


class ClickRelations(Recipe):
    repo = "click"
    family = "relations"
    summary = "Option relations on click.Option: conflicts_with / requires / exclusive groups"
    CORE = ("core",)
    ALL_RULES = [
        Rule("core", "Conflicting options",
             "`click.Option` (and therefore `@click.option`) gains a keyword `conflicts_with`: a sequence of "
             "*parameter names* (the Python names, e.g. `\"bravo\"`, not flags). When the option and any option it "
             "names are both *provided*, parsing fails with `click.UsageError` (exit code 2) before the command "
             "callback runs. An option is *provided* when its value came from the command line "
             "(`ctx.get_parameter_source(name) is ParameterSource.COMMANDLINE`) - defaults, `default_map` and "
             "environment variables do not count. Names that match no option of the command, and an option's "
             "own name, are ignored. A pair that declares the conflict on both sides is reported once. The error "
             "message mentions, for every option involved in a reported violation, that option's first declared "
             "option string (for example `--alpha`), and no other option string. The check runs once per command "
             "in `Command.parse_args`, after all parameters were processed."),
        Rule("requires", "Required companions",
             "A second keyword `requires` (sequence of parameter names): if the option is provided, every "
             "named option must be provided as well; each missing one is a violation involving both options. "
             "Unknown names and the option's own name are ignored."),
        Rule("env", "Environment counts as provided",
             "Values that came from an environment variable "
             "(`ParameterSource.ENVIRONMENT`) also count as *provided* for every relation."),
        Rule("falsy", "Falsy values do not count",
             "An option whose converted value is falsy (`0`, an empty string, a boolean flag set to `False` as "
             "by `--no-echo`, an empty tuple) does not count as provided even if it appeared on the command line."),
        Rule("groups", "Exclusive groups",
             "A third keyword `exclusive_group` (a string, default `None`): at most one provided option of the "
             "same group is allowed. If several are provided that is a single violation involving all provided "
             "members of that group."),
        Rule("all", "Report every violation",
             "Violations are found by scanning the command's options in declaration order: for each provided "
             "option, first its `conflicts_with` names in listed order, then its `requires` names in listed order; "
             "group violations come after all per-option violations, ordered by the declaration position of the "
             "group's first provided member. The raised `UsageError` reports all violations, one per line "
             "(without this rule: only the first violation is reported)."),
        Rule("resilient", "Completion safe",
             "No relation is checked when `ctx.resilient_parsing` is true (shell completion must never fail "
             "on an incomplete combination)."),
        Rule("help", "Shown in --help",
             "In `--help`, an option's help record shows its relations as extra items *after* any existing "
             "bracketed items (`env var`, `default`, `range`, `required`), inside the same brackets and joined "
             "with `; `: first `conflicts with: <flags>` (listed names that match an option, in listed order, "
             "shown as that option's first declared option string, joined with `, `), then, if requires is "
             "implemented, `requires: <flags>` likewise. Nothing is added for an option without matching names."),
    ]

    def title(self, v): return "Add option relations (`conflicts_with`, `requires`, exclusive groups) to `click.Option`"
    def preamble(self, v):
        return ("Command-line tools often need rules such as \"`--json` and `--csv` cannot be combined\". Click "
                "has no declarative support, so every application re-implements it in callbacks. Add it to "
                "`click.Option`. The hidden tests build commands with options named `alpha`..`hotel` and the "
                "exact kwargs described below.")

    # -------------------------------------------------------------- oracle
    def _provided(self, name, args_vals, env_vals, R):
        src = None
        if name in args_vals:
            src, val = "cli", args_vals[name]
        elif name in env_vals:
            src, val = "env", env_vals[name]
        else:
            return False
        if src == "env" and "env" not in R:
            return False
        if "falsy" in R and not val:
            return False
        return True

    def model(self, args, env, R):
        """-> None if ok, else list of violations; each violation = list of flag strings."""
        vals, i = {}, 0
        while i < len(args):
            a = args[i]
            n = a[2:]
            if n in ("no-echo", "no-hotel"):
                vals[n[3:]] = False; i += 1
            elif n in ("echo", "hotel"):
                vals[n] = True; i += 1
            else:
                vals[n] = args[i + 1] if n in ("alpha", "bravo", "delta", "foxtrot") else int(args[i + 1])
                i += 2
        envv = {"bravo": env["TFRULES_BRAVO"]} if "TFRULES_BRAVO" in env else {}
        prov = lambda n: self._provided(n, vals, envv, R)
        requires = {"charlie": ["delta"]}
        out, seen = [], set()
        for o in OPTS:
            if not prov(o):
                continue
            for n in CONFLICTS.get(o, []):
                if n == o or n not in OPTS or not prov(n):
                    continue
                p = frozenset((o, n))
                if p not in seen:
                    seen.add(p); out.append([f"--{o}", f"--{n}"])
            if "requires" in R:
                for n in requires.get(o, []):
                    if n in OPTS and n != o and not prov(n):
                        out.append([f"--{o}", f"--{n}"])
        if "groups" in R:
            mem = [o for o in OPTS if o in GROUP and prov(o)]
            if len(mem) > 1:
                out.append([f"--{m}" for m in mem])
        if not out:
            return None
        return out if "all" in R else out[:1]

    # -------------------------------------------------------------- implementation
    def impl_edits(self, v, rules):
        api = set(v.rules)  # public signature follows the full spec; behaviour follows `rules`
        has = rules.__contains__
        sig = "        conflicts_with: cabc.Sequence[str] = (),\n"
        store = "        self.conflicts_with = tuple(conflicts_with)\n"
        if "requires" in api:
            sig += "        requires: cabc.Sequence[str] = (),\n"; store += "        self.requires = tuple(requires)\n"
        if "groups" in api:
            sig += "        exclusive_group: str | None = None,\n"; store += "        self.exclusive_group = exclusive_group\n"
        L = []; a = L.append
        a("    def _check_option_relations(self, ctx: Context) -> None:")
        a('        """Fail with a usage error for ``conflicts_with`` / ``requires`` violations."""')
        if has("resilient"):
            a("        if ctx.resilient_parsing:\n            return\n")
        a("        options = [p for p in self.get_params(ctx) if isinstance(p, Option)]")
        a("        by_name = {p.name: p for p in options}\n")
        a("        def provided(param: Option) -> bool:")
        a("            source = ctx.get_parameter_source(param.name)")
        env_ok = " or source is ParameterSource.ENVIRONMENT" if has("env") else ""
        a(f"            if not (source is ParameterSource.COMMANDLINE{env_ok}):\n                return False")
        if has("falsy"):
            a("            return bool(ctx.params.get(param.name))")
        else:
            a("            return True")
        a("\n        violations: list[list[Option]] = []\n        seen: set[frozenset[str | None]] = set()")
        a("        for opt in options:\n            if not provided(opt):\n                continue")
        a("            for name in opt.conflicts_with:\n                other = by_name.get(name)")
        a("                if other is None or other is opt or not provided(other):\n                    continue")
        a("                pair = frozenset((opt.name, other.name))\n                if pair not in seen:\n                    seen.add(pair)\n                    violations.append([opt, other])")
        if has("requires"):
            a("            for name in opt.requires:\n                other = by_name.get(name)")
            a("                if other is not None and other is not opt and not provided(other):\n                    violations.append([opt, other])")
        if has("groups"):
            a("\n        groups: dict[str, list[Option]] = {}\n        for opt in options:\n            if opt.exclusive_group is not None and provided(opt):")
            a("                groups.setdefault(opt.exclusive_group, []).append(opt)")
            a("        violations.extend(members for members in groups.values() if len(members) > 1)")
        a("\n        if not violations:\n            return")
        if not has("all"):
            a("        violations = violations[:1]")
        a("        lines = [\n            _(\"Conflicting or incomplete options: {options}.\").format(\n                options=\", \".join(o.opts[0] for o in group)\n            )\n            for group in violations\n        ]")
        a("        raise UsageError(\"\\n\".join(lines), ctx=ctx)\n")
        method = "\n".join(L) + "\n"
        edits = [
            Edit("src/click/core.py", "replace",
                 "        deprecated: bool | str = False,\n" + sig + "        **attrs: t.Any,\n    ) -> None:\n        super().__init__(\n            param_decls,\n            type=type,\n            multiple=multiple,",
                 anchor="        deprecated: bool | str = False,\n        **attrs: t.Any,\n    ) -> None:\n        super().__init__(\n            param_decls,\n            type=type,\n            multiple=multiple,"),
            Edit("src/click/core.py", "insert_before", store + "\n", anchor="        # Phase 1: prompt-related attributes."),
            Edit("src/click/core.py", "insert_before", "        self._check_option_relations(ctx)\n\n",
                 anchor="        if args and not ctx.allow_extra_args and not ctx.resilient_parsing:\n            ctx.fail(\n                ngettext(\n                    \"Got unexpected extra argument ({args})\","),
            Edit("src/click/core.py", "insert_before", method + "\n",
                 anchor="    def invoke(self, ctx: Context) -> t.Any:\n        \"\"\"Given a context, this invokes the attached callback (if it exists)"),
        ]
        if has("help"):
            body = ("        by_name = {p.name: p for p in ctx.command.get_params(ctx) if isinstance(p, Option)}\n"
                    "        for attr, label in ((\"conflicts_with\", _(\"conflicts with\")),"
                    + (" (\"requires\", _(\"requires\"))" if "requires" in api else "") + "):\n"
                    "            flags = [by_name[n].opts[0] for n in getattr(self, attr) if n in by_name]\n"
                    "            if flags:\n                extra_items.append(f\"{label}: {', '.join(flags)}\")\n\n")
            edits.append(Edit("src/click/core.py", "insert_before", body,
                              anchor="        if extra_items:\n            extra_str = \"; \".join(extra_items)"))
        return edits

    # -------------------------------------------------------------- tests
    def feature_test_paths(self, v): return ["tests/test_task_relations.py"]

    def _scenarios(self, seed, n=1500):
        rng = random.Random(seed)
        out = []
        for _ in range(n):
            args = []
            for o in rng.sample(OPTS, rng.randint(1, 6)):
                if o in FLAGS:
                    args.append(rng.choice(FLAGS[o]))
                else:
                    args += [f"--{o}", rng.choice(VALUE[o])]
            env = {"TFRULES_BRAVO": "e"} if rng.random() < 0.25 else {}
            out.append((args, env))
        return out

    def test_edits(self, v):
        R = set(v.rules)
        pool = self._scenarios(v.seed * 7 + 1)
        sections = []
        for rid in v.rules:
            if rid in ("resilient", "help"):
                continue
            drop = {rid} | {x for x in v.rules if rid in self.rule(x).needs}
            full, abl = R, R - drop
            if rid == "core":
                only = {"core"}
                cand = [(a, e) for a, e in pool if self.model(a, e, R) == self.model(a, e, only)]
                ok = [c for c in cand if self.model(*c, R) is None][:4]
                bad = [c for c in cand if self.model(*c, R) is not None][:5]
                chosen = ok + bad
            else:
                disc = [(a, e) for a, e in pool if self.model(a, e, full) != self.model(a, e, abl)]
                disc.sort(key=lambda c: (len(c[0]), len(c[1])))
                if not disc:
                    raise RuntimeError(f"no discriminating scenario for rule {rid} in {v.id}")
                # also keep scenarios that exercise many options yet are *accepted* (satisfied relations):
                # these kill mutants that over-report violations
                okc = [c for c in pool if self.model(*c, full) is None and self.model(*c, abl) is None]
                okc.sort(key=lambda c: -len(c[0]))
                chosen = disc[:5] + okc[:2]
            sections.append((rid, [(a, e, self.model(a, e, R)) for a, e in chosen]))
        decl = [
            ("alpha", ["--alpha", "-a"], "str", "conflicts_with=('bravo', 'ghost'), help='Alpha mode.'"),
            ("bravo", ["--bravo", "-b"], "str", "envvar='TFRULES_BRAVO', default='b0', show_default=True, conflicts_with=('alpha',)"),
            ("charlie", ["--charlie", "-c"], "int", "conflicts_with=('echo',)" + (", requires=('delta',)" if "requires" in R else "") + ", help='Charlie level.'"),
            ("delta", ["--delta", "-d"], "str", ""),
            ("echo", ["--echo/--no-echo"], "flag", ""),
        ]
        grp = ", exclusive_group='mode'" if "groups" in R else ""
        decl += [("foxtrot", ["--foxtrot"], "str", grp.lstrip(", ")), ("golf", ["--golf"], "int", grp.lstrip(", ")),
                 ("hotel", ["--hotel/--no-hotel"], "flag", grp.lstrip(", "))]
        deco = []
        for name, flags, kind, kw in decl:
            ty = {"str": "", "int": ", type=int", "flag": ""}[kind]
            deco.append(f"@click.option({', '.join(repr(f) for f in flags)}{ty}{', ' + kw if kw else ''})")
        params = ", ".join(n for n, *_ in decl)
        lines = ['"""Hidden tests for the option-relations task (generated; `rule_<id>` tags)."""',
                 "import re", "", "import click", "import pytest", "from click.testing import CliRunner", "", "",
                 "def make():", "    @click.command(context_settings={'terminal_width': 200})", *["    " + d for d in deco],
                 f"    def cli({params}):", "        click.echo('RAN')", "", "    return cli", "", "",
                 "def _flags(output):", "    msg = output.split('Error:', 1)[1]", "    return set(re.findall(r'--[a-z]+', msg))", "", "",
                 "def _check(args, env, expected):",
                 "    res = CliRunner().invoke(make(), args, env=env)",
                 "    if expected is None:", "        assert res.exit_code == 0 and 'RAN' in res.output, res.output",
                 "    else:",
                 "        assert res.exit_code == 2 and 'RAN' not in res.output, (args, env, res.output)",
                 "        assert _flags(res.output) == {f for viol in expected for f in viol}, (args, env, res.output)",
                 "        if len(expected) > 1:",
                 "            assert len(res.output.split('Error:', 1)[1].strip().splitlines()) == len(expected), res.output", "", ""]
        for rid, rows in sections:
            body = ",\n    ".join(f"({a!r}, {e!r}, {x!r})" for a, e, x in rows)
            lines += [f"CASES_{rid.upper()} = [\n    {body},\n]", "",
                      f"@pytest.mark.parametrize('args,env,expected', CASES_{rid.upper()}, ids=[f'c{{i}}' for i in range(len(CASES_{rid.upper()}))])",
                      f"def test_rule_{rid}(args, env, expected):", "    _check(args, env, expected)", "", ""]
        if "resilient" in R:
            lines += ["def test_rule_resilient():", "    cmd = make()",
                      "    with pytest.raises(click.UsageError):", "        cmd.make_context('cli', ['--alpha', 'x', '--bravo', 'y'])",
                      "    ctx = cmd.make_context('cli', ['--alpha', 'x', '--bravo', 'y'], resilient_parsing=True)",
                      "    assert ctx.params['alpha'] == 'x'", "", ""]
        if "help" in R:
            req = "; requires: --delta" if "requires" in R else ""
            lines += ["def test_rule_help():", "    out = ' '.join(CliRunner().invoke(make(), ['--help']).output.split())",
                      "    assert '[conflicts with: --bravo]' in out", "    assert '[default: b0; conflicts with: --alpha]' in out",
                      f"    assert '[conflicts with: --echo{req}]' in out", "    assert 'ghost' not in out", ""]
        return [Edit("tests/test_task_relations.py", "create", "\n".join(lines) + "\n", role="test")]
