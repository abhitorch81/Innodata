# Coding Task Factory (Innodata hackathon, Track 1)

**One reusable strategy** that turns a working repository into validated feature-development tasks for evaluating AI coding systems:
**rule-algebra task synthesis + ablation / mutation / cross-task validation.** No LLM is needed to run it (deterministic, offline, reproducible); an LLM could later author recipes and the same validators would gate them.

## The idea
A task is *data*: a family plus a sampled set of independent behavioural **rules** (e.g. for a duration parser: `compound`, `ordered`, `bare`, `fraction`, `case`, `negative`, `spaces`, `bounds`). From that single object we derive:
- **PROBLEM.md** - one precise requirement per rule (the only spec a solver sees),
- **reference.patch** - an implementation generated from the rule set (anchor-based edits at the pinned base commit),
- **tests.patch** - hidden tests where every test is tagged `rule_<id>`; expected values come from an **independent oracle** (a different algorithm from the implementation), and cases are chosen because they **discriminate** each rule.

Because requirements, implementation and tests come from the same rule objects, they cannot drift apart. Tasks differ in behaviour (which rules interact), not in wording.

## Validation evidence (7 stages per task, in `validation.json`)
| Stage | Proves |
|---|---|
| S1 | feature tests fail on the untouched base commit |
| S2 | reference implementation passes all feature tests |
| S3 | repo's existing test-suite still passes (pass-to-pass) |
| S4 | **rule ablation**: for each rule an implementation that is right except for that rule is built; tests attributed to that rule must fail |
| S5 | **mutation testing** of the reference (flipped operators, off-by-one, negated conditions; timeouts count as kills); survivors listed |
| S6 | **regression guard**: mutants of pre-existing neighbouring code must be caught by the existing suite / feature tests |
| S7 | determinism |

Plus a **cross-task variation matrix**: task *i*'s tests run against task *j*'s reference; off-diagonal < 1.0 proves the tasks demand different behaviour.

## Task package (`tasks/<repo>/<family>-NN/`)
`task.json` (schema `taskfactory/1`: repo URL, **base_commit**, language, commands, fail-to-pass / pass-to-pass lists, rules, difficulty), `PROBLEM.md`, `reference.patch`, `tests.patch`, `variant.json`, `validation.json`.

## Results (19 tasks, 5 families, 3 repos; all pass the gates)
| Repo | Family | Tasks | Mutation kill | Cross-task pass rate (off-diagonal) |
|---|---|---|---|---|
| click | duration | 4 | 91-100% | 0.53-0.84 |
| click | relations | 4 | 92-100% | 0.00-0.84 |
| jsoncpp | merge | 4 | 87-100% | 0.59-0.87 |
| jsoncpp | arrayinline | 4 | 81-88% | 0.09-0.96 |
| zod | unique | 3 | 89-91% | 0.46-0.89 |

Existing-suite baselines held by every task: click 2653 tests, jsoncpp 133 (+ guard tests), zod 2875.
`python -m taskfactory report` regenerates `report.html` (dashboard) from the packages. Design and code walkthrough: `docs/BUILD_PLAN.md`.

## Run it
```bash
scripts/setup.sh                                   # clones repos at pinned commits, installs tooling
.venv/bin/python -m taskfactory list
.venv/bin/python -u -m taskfactory build --repo click --family duration -n 4 --mutants 12
.venv/bin/python -m taskfactory evaluate tasks/click/duration-03 tasks/click/duration-03/reference.patch
.venv/bin/python scripts/demo_eval.py tasks/click/duration-03   # grade correct / incomplete / tampering candidates
.venv/bin/python -m taskfactory report && open report.html
```
`evaluate` grades any candidate patch: RESOLVED / UNRESOLVED with a **per-requirement score**, and REJECTED if the patch edits protected tests.

## Families
| Repo | Family | What the task asks for |
|---|---|---|
| click (Python) | `duration` | new `click.Duration` ParamType, 8 optional rules |
| click | `relations` | `conflicts_with` / `requires` / exclusive groups on `Option` (edits existing core code) |
| jsoncpp (C++) | `merge` | `Json::Value::merge` deep merge, 8 optional rules |
| jsoncpp | `arrayinline` | new `StreamWriterBuilder` setting (edits existing writer) |
| zod (TS) | `unique` | `ZodArray.unique()`: key / deep equality / per-index issues / type-level typed callback (typecheck project) |

See `LIMITATIONS.md` for an honest statement of scope and weaknesses.

## Interactive app (three.js + GSAP)

```bash
.venv/bin/python app/server.py 8765   # live: http://localhost:8765  (real grader + live build)
python app/make_static.py             # regenerates app/factory-static.html (single file, recorded evidence)
```
Three stations: **Atlas** (all tasks), **Pipeline** (S1–S7 gates, click a rule orb to ablate it, grade candidates),
**Variation** (cross-task matrix). **Lab** composes new tasks from rules and builds them live; **Play** lists
interactions. Add your own in `app/custom-interactions.js` via `TaskFactoryApp.registerInteraction({...})`.
