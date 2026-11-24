# Build plan and code walkthrough

## 1. How we approached it (in order)

| Step | Decision | Why |
|---|---|---|
| 1. Read the brief | Score weights: repeatability 25, validity evidence 25, variation 20, judgement 15, impact 15 | Every design choice maps to a criterion |
| 2. Check the repos | Baselines first: click 2653 tests, jsoncpp 133, zod 2875 | A task is only meaningful if the base suite is green and runnable |
| 3. Pick the strategy | **Rule-algebra synthesis**: a task is a sampled set of independent behavioural rules | Gives variation in *behaviour*, and one source of truth |
| 4. Build the generic core | `core.py`, `validate.py`, `mutate.py`, `factory.py` | Reusable across repos and languages (repeatability) |
| 5. Prove it on one repo | click `Duration`, end to end | Debug the framework on the fastest repo |
| 6. Add a language adapter per repo | pytest, g++, vitest | Isolates language-specific glue |
| 7. Add a second, harder family per repo | click `relations`, jsoncpp `arrayinline`: these edit *existing* code | Makes regression evidence (S6) meaningful |
| 8. Validate, find weaknesses, fix | See section 4 | The validators found real bugs in our own tasks |
| 9. Package, grade, report | `evaluate`, `report.py`, README | Practical impact and demo |

## 2. Architecture in one picture

```
Recipe (rules + oracle + templates)
   -> Variant (family, rules, params)           core.py
   -> PROBLEM.md / reference.patch / tests.patch
   -> validate(): S1..S7 evidence                validate.py
   -> package(): tasks/<repo>/<family>-NN/       factory.py
   -> evaluate(candidate.patch) / report         factory.py, report.py
Adapter: runs the repo's own tests, returns RunResult(passed, failed, build_ok)
```

## 3. Code walkthrough

### 3.1 `core.py`: the data model
- `Edit(path, kind, text, anchor, role)`: a deterministic, anchor-based source edit. It fails loudly if the anchor is missing or ambiguous, which also detects repo drift.
- `Rule(id, title, requirement, needs)`: one behavioural requirement. The `requirement` string is the *only* spec a solver sees.
- `Variant(family, seed, rules, params)`: one task, as data.
- `Recipe.sample(n, seed)`: draws distinct rule subsets, closed under `needs`. The seed makes it reproducible.
- `Recipe.ablation_sets(v)`: for each rule, the rule set with that rule (and its dependents) removed.
- `Workspace`: a git worktree pinned to the base commit. `reset()`, `apply(edits)`, `diff()` produce the patches.

### 3.2 A recipe (example: `recipes/click_duration.py`)
A recipe supplies three derivations from one `Variant`:
1. **Requirements:** `Rule.requirement` text per enabled rule.
2. **Implementation:** `impl_edits(v, rules)` renders code from the rule set. Passing a *smaller* rule set yields an ablated (deliberately wrong) implementation.
3. **Tests:** `test_edits(v)` renders tests. Cases come from a candidate pool and are kept only if `model(full) != model(ablated)`.

The oracle `model()` is an independent scanner-style implementation. The reference uses regexes, so a shared bug between them is unlikely.

### 3.3 `validate.py`: the seven stages
```
S1 tests-alone on base       every rule needs >=1 failing test; passing ones become guard tests
S2 base + reference + tests  all feature tests pass
S3 full existing suite       still passes
S4 for each rule: build ablated impl, run tests -> a test tagged with that rule must fail
S5 mutate the reference (edit_mutants), run tests; killed / survived / invalid (stillborn)
S6 mutate pre-existing neighbours of the patch; caught by existing suite or feature tests?
S7 run twice -> identical
```
Gate = S1-S4 + S7. S5 and S6 are reported scores. Test IDs embed `rule_<id>` so failures are attributed to requirements.

### 3.4 `mutate.py`
Regex operators (`==`/`!=`, `<`/`<=`, `and`/`or`, `+`/`-`, int+1, drop `not`, `[0]`->`[-1]`) plus condition negation. Applied to the text of the reference edits, so each mutant is the reference with one plausible bug. A runner timeout counts as a kill (a mutant once produced an infinite loop).

### 3.5 Adapters
| Adapter | Runs | Notable handling |
|---|---|---|
| `python_pytest.py` | pytest + junit XML, `PYTHONPATH` to the worktree | timeout -> `failed={"<timeout>"}` |
| `cpp_gpp.py` | g++ with the repo's own `jsontest` runner, cached per-file objects | compile failure -> `build_ok=False` |
| `ts_vitest.py` | vitest JSON; zod's typecheck project makes **type-level requirements real tests** | `tsc` check on source; flaky-test retry |

### 3.6 `factory.py`
- `package()` writes `task.json` (schema `taskfactory/1`, includes `base_commit`), patches, test-ID lists and `validation.json`.
- `variation_matrix()` runs task *i*'s tests against task *j*'s reference.
- `evaluate()` applies a candidate patch plus the hidden tests and returns RESOLVED / UNRESOLVED with per-requirement scores. REJECTED if the patch touches protected test files.

## 4. What the validators caught in our own work (honest log)
| Finding | Stage | Fix |
|---|---|---|
| Oracle applied `bounds` to tests that never construct a bounded type | S2 | Evaluate non-bounds tests without bounds |
| Reference imported `decimal` at module load; click's own `test_light_imports` failed | S3 | Lazy import. The existing suite did its job |
| A mutant looped forever and hung the run | S5 | Per-run timeouts; timeout = kill |
| Survivors showed single-flag options could not distinguish "first" from "last" option string | S5 | Test options now have aliases |
| No test for a satisfied `requires` | S5 | Keep accepted cases that exercise many options |
| A rule whose correct behaviour is "stay as before" has no failing test on base | S1 | S1 now requires one failing test *per rule*; the rest are guard tests (pass-to-pass) |
| Grader split test IDs on spaces (2912 fragments vs 2653 IDs) | evaluate | Read ID lists line by line |

## 5. Limits (full list in `LIMITATIONS.md`)
Recipes are authored templates; difficulty labels are an uncalibrated heuristic; no LLM solver was run; oracles are ours; mutation operators are simple, and some survivors are equivalent mutants.
