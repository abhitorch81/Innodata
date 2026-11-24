"""zod / ZodArray.unique(): reject arrays with duplicate items.

Rule algebra over {key, deep, nullish, perindex, firstonly, firstidx, message, types}. Behavioural rules are checked
at runtime; `types` is a TYPE-level requirement checked by zod's typecheck vitest project (@ts-expect-error).
The independent oracle `model` is a Python model of the semantics over a small tagged-value algebra."""
from __future__ import annotations
import json
import math
import random
from ..core import Recipe, Rule, Edit

UNDEF = "<undefined>"
TEST = "packages/zod/src/v4/classic/tests/task-unique.test.ts"
SCHEMAS = "packages/zod/src/v4/classic/schemas.ts"


# --------------------------------------------------------------- tagged values
def norm(v):
    if v is UNDEF:
        return ("undef",)
    if v is None:
        return ("null",)
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, (int, float)):
        return ("num", "nan" if isinstance(v, float) and math.isnan(v) else float(v) + 0.0)
    if isinstance(v, str):
        return ("str", v)
    raise TypeError(v)


def js(v):
    if v is UNDEF: return "undefined"
    if v is None: return "null"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, float) and math.isnan(v): return "NaN"
    if isinstance(v, float) and v == 0 and math.copysign(1, v) < 0: return "-0"
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, str): return json.dumps(v)
    if isinstance(v, tuple) and v[0] == "D": return f"new Date({v[1]})"
    if isinstance(v, list): return "[" + ", ".join(js(x) for x in v) + "]"
    if isinstance(v, dict): return "{" + ", ".join(f"{k}: {js(x)}" for k, x in v.items()) + "}"
    raise TypeError(v)


class Obj:
    """An object/array/Date item. `ref` shared between items = the very same JS object (identity)."""
    def __init__(self, struct, ref=None): self.struct, self.ref = struct, ref


def sv0(a, b):
    if isinstance(a, Obj) or isinstance(b, Obj):
        return isinstance(a, Obj) and isinstance(b, Obj) and a.ref is not None and a.ref == b.ref
    return norm(a) == norm(b)


def deep(a, b):
    if isinstance(a, Obj) and isinstance(b, Obj):
        if a.ref is not None and a.ref == b.ref:
            return True
        return deep(a.struct, b.struct)
    if isinstance(a, Obj) or isinstance(b, Obj):
        return False
    if isinstance(a, tuple) and isinstance(b, tuple):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(deep(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(deep(a[k], b[k]) for k in a)
    if isinstance(a, (list, dict, tuple)) or isinstance(b, (list, dict, tuple)):
        return False
    return norm(a) == norm(b)


class ZodUnique(Recipe):
    repo = "zod"
    family = "unique"
    summary = "`ZodArray.unique()` - duplicate detection with keys, deep equality, per-index issues, typed callbacks"
    CORE = ("core",)
    ALL_RULES = [
        Rule("core", "Basic uniqueness",
             "Add a method `unique(options?)` to `ZodArray` (classic API, `packages/zod/src/v4/classic/schemas.ts`) that "
             "adds a check and returns the same schema type (`this`). The check fails when two items of the array are "
             "equal under SameValueZero (the `Set` rule: `NaN` equals `NaN`, `0` equals `-0`, `\"1\"` does not equal `1`, "
             "`null` does not equal `undefined`, two distinct objects are never equal even if they look alike, the same "
             "object twice is). Items are compared as the *parsed output* values (so with `z.string().trim()` the "
             "items `\" a\"` and `\"a\"` are duplicates). Every issue it reports has `code: \"custom\"` and a non-empty "
             "`message`. An array without duplicates passes; the empty array and one-element arrays pass."),
        Rule("key", "Uniqueness by key",
             "`options.by` is an optional function `(item, index) => unknown`; when given, the keys it returns "
             "(instead of the items) are compared for equality."),
        Rule("deep", "Structural equality",
             "`options.deep: true` compares by structure instead of identity: arrays element-wise, plain objects "
             "by own enumerable keys irrespective of key order, `Date` by `getTime()`, everything else by SameValueZero. "
             "It applies to items or, when `by` is used, to the returned keys."),
        Rule("nullish", "Ignore nullish",
             "`options.ignoreNullish: true`: items (or keys, when `by` is used) that are `null` or `undefined` never "
             "count as duplicates of each other."),
        Rule("perindex", "One issue per duplicate",
             "Instead of one issue for the whole array, report one issue for every duplicate occurrence, i.e. every item that "
             "equals some EARLIER item (the first occurrence is never reported). Each issue's `path` is `[index]` "
             "of that item, relative to the array (so inside `z.object({{ tags }})` the full path is `[\"tags\", index]`), "
             "and issues are ordered by index. Without this behaviour there is exactly one issue and its `path` is "
             "the array's own (empty at top level)."),
        Rule("firstonly", "First duplicate only", "Only the issue for the first duplicate occurrence (lowest index) "
             "is reported.", needs=("perindex",)),
        Rule("firstidx", "Index of first occurrence", "Each per-duplicate issue carries `params: {{ firstIndex }}` "
             "= the index of the earliest item it equals.", needs=("perindex",)),
        Rule("message", "Custom message", "`options.message` (a string) is used as the `message` of every issue the "
             "check reports."),
        Rule("types", "Typed callback", "Type level: the `by` callback's first parameter is typed as the array's "
             "OUTPUT element type (`z.array(z.string()).unique({ by: (s) => s.length })` compiles, while a callback "
             "taking `number` is a compile error), and `unique` is typed to return the same schema type.",
             needs=("key",)),
    ]

    def title(self, v): return "Add `.unique()` to `ZodArray`"
    def preamble(self, v):
        return ("Zod can bound the length of arrays but cannot say \"no duplicates\". Add a `unique` check to arrays "
                "following the style of the existing array methods. The hidden tests are vitest tests including "
                "type-level (`@ts-expect-error`) assertions.")

    def feature_test_paths(self, v): return [TEST]
    def regression_subset(self, v):
        d = "packages/zod/src/v4/classic/tests/"
        return [d + f for f in ("array.test.ts", "refine.test.ts", "custom.test.ts", "nested-refine.test.ts")]

    # ------------------------------------------------------------------ oracle
    def model(self, items, opts, R):
        by = opts.get("by") if "key" in R else None
        def key(it):
            if by == "id":
                return it.struct.get("id", UNDEF)
            if by == "lower":
                return it.lower()
            return it
        keys = [key(x) for x in items]
        eq = deep if ("deep" in R and opts.get("deep")) else sv0
        skip_nullish = "nullish" in R and opts.get("ignoreNullish")
        dups = []
        for i, k in enumerate(keys):
            if skip_nullish and (k is None or k is UNDEF):
                continue
            for j in range(i):
                if eq(keys[j], k):
                    dups.append((i, j)); break
        if not dups:
            return []
        msg = opts.get("message") if "message" in R else None
        if "perindex" in R:
            sel = dups[:1] if "firstonly" in R else dups
            out = []
            for i, j in sel:
                d = {"code": "custom", "path": [i]}
                if "firstidx" in R: d["params"] = {"firstIndex": j}
                if msg is not None: d["message"] = msg
                out.append(d)
            return out
        d = {"code": "custom", "path": []}
        if msg is not None: d["message"] = msg
        return [d]

    # ------------------------------------------------------------------ implementation
    def impl_edits(self, v, rules):
        api, has = set(v.rules), rules.__contains__
        opt = []
        if "key" in api:
            opt.append(f"    by?: (item: {'core.output<T>' if has('types') else 'any'}, index: number) => unknown;")
        if "deep" in api: opt.append("    deep?: boolean;")
        if "nullish" in api: opt.append("    ignoreNullish?: boolean;")
        if "message" in api: opt.append("    message?: string;")
        iface = ("  unique(options?: {\n" + "\n".join(opt) + "\n  }): this;\n") if opt else "  unique(): this;\n"
        helpers = '''function _uniqueSameValueZero(a: unknown, b: unknown): boolean {
  return a === b || (a !== a && b !== b);
}

'''
        deep_helper = '''function _uniqueDeepEqual(a: any, b: any): boolean {
  if (_uniqueSameValueZero(a, b)) return true;
  if (a instanceof Date && b instanceof Date) return a.getTime() === b.getTime();
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((x, i) => _uniqueDeepEqual(x, b[i]));
  }
  const plain = (x: any) => x !== null && typeof x === "object" && Object.getPrototypeOf(x) === Object.prototype;
  if (plain(a) && plain(b)) {
    const ka = Object.keys(a);
    return (
      ka.length === Object.keys(b).length &&
      ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && _uniqueDeepEqual(a[k], b[k]))
    );
  }
  return false;
}

'''
        if has("deep"):
            helpers += deep_helper
        B = []; a = B.append
        a("    unique(options) {")
        a("      return this.check((ctx) => {")
        a("        const items = ctx.value as unknown[];")
        a("        const keys = items.map((item, i) => (options?.by ? options.by(item as any, i) : item));" if has("key")
          else "        const keys = items;")
        a("        const equal = options?.deep ? _uniqueDeepEqual : _uniqueSameValueZero;" if has("deep")
          else "        const equal = _uniqueSameValueZero;")
        a("        const duplicates: { index: number; first: number }[] = [];")
        a("        for (let i = 0; i < keys.length; i++) {")
        if has("nullish"):
            a("          if (options?.ignoreNullish && keys[i] == null) continue;")
        a("          for (let j = 0; j < i; j++) {")
        a("            if (equal(keys[j], keys[i])) {\n              duplicates.push({ index: i, first: j });\n              break;\n            }")
        a("          }\n        }")
        a("        if (!duplicates.length) return;")
        msg = "options?.message ?? " if has("message") else ""
        if has("perindex"):
            lst = "duplicates.slice(0, 1)" if has("firstonly") else "duplicates"
            par = "\n            params: { firstIndex: d.first }," if has("firstidx") else ""
            a(f"        for (const d of {lst}) {{")
            a(f"          ctx.issues.push({{\n            code: \"custom\",\n            input: ctx.value,\n            path: [d.index],{par}\n            message: {msg}\"Duplicate item in array\",\n          }});")
            a("        }")
        else:
            a(f"        ctx.issues.push({{\n          code: \"custom\",\n          input: ctx.value,\n          message: {msg}\"Array contains duplicate items\",\n        }});")
        a("      });\n    },")
        return [
            Edit(SCHEMAS, "insert_before", helpers, anchor="// ZodArray\nexport interface ZodArray<T extends core.SomeType = core.$ZodType>"),
            Edit(SCHEMAS, "insert_before", iface, anchor="\n  unwrap(): T;\n  \"~standard\": ZodStandardSchemaWithJSON<this>;\n}\nexport const ZodArray:"),
            Edit(SCHEMAS, "insert_before", "\n".join(B) + "\n",
                 anchor="    unwrap() {\n      return this.element;\n    },\n  }\n);\n\nexport function array<"),
        ]

    # ------------------------------------------------------------------ tests
    def _case(self, rng, R):
        kind = rng.choice(["prim", "prim", "obj", "str", "nested"])
        n = rng.randint(2, 6)
        opts = {}
        if kind == "prim":
            pool = [1, "1", 2, 0, -0.0, float("nan"), None, UNDEF, True, "a", 1, "a"]
            items = [rng.choice(pool) for _ in range(n)]
        elif kind == "str":
            items = [rng.choice(["a", "A", "b", "B", "c"]) for _ in range(n)]
            if rng.random() < .6: opts["by"] = "lower"
        elif kind == "obj":
            items = []
            for k in range(n):
                i = rng.choice([1, 2, 3, None, UNDEF])
                st = {} if i is UNDEF else {"id": i}
                items.append(Obj({**st, "tag": rng.choice(["x", "y"])}, ref=(f"r{rng.randint(1, 3)}" if rng.random() < .3 else None)))
            # items sharing a ref must be structurally identical
            seen = {}
            for it in items:
                if it.ref in seen: it.struct = seen[it.ref]
                elif it.ref: seen[it.ref] = it.struct
            if rng.random() < .6: opts["by"] = "id"
        else:
            vals = [[1, 2], [1, 2], [2, 1], {"a": 1, "b": 2}, {"b": 2, "a": 1}, {"a": 1}, ("D", 1000), ("D", 1000), ("D", 2000), [{"a": [1]}], [{"a": [1]}]]
            items = [Obj(rng.choice(vals), ref=(f"r{rng.randint(1, 2)}" if rng.random() < .2 else None)) for _ in range(n)]
            seen = {}
            for it in items:
                if it.ref in seen: it.struct = seen[it.ref]
                elif it.ref: seen[it.ref] = it.struct
        if "deep" in R and rng.random() < .6: opts["deep"] = True
        if "nullish" in R and rng.random() < .5: opts["ignoreNullish"] = True
        if "message" in R and rng.random() < .5: opts["message"] = "dupe!"
        return items, opts

    def _render(self, items, opts, expected, name, rules):
        refs = {}
        src = []
        for it in items:
            if isinstance(it, Obj) and it.ref and it.ref not in refs:
                refs[it.ref] = True
                src.append(f"    const {it.ref} = {js(it.struct)};")
        arr = ", ".join((it.ref if isinstance(it, Obj) and it.ref else js(it.struct)) if isinstance(it, Obj) else js(it) for it in items)
        o = []
        if "by" in opts: o.append("by: (x: any) => " + ("x.id" if opts["by"] == "id" else "x.toLowerCase()"))
        if opts.get("deep"): o.append("deep: true")
        if opts.get("ignoreNullish"): o.append("ignoreNullish: true")
        if "message" in opts: o.append(f"message: {json.dumps(opts['message'])}")
        call = f"unique({{ {', '.join(o)} }})" if o else "unique()"
        body = [f"test({json.dumps(name)}, () => {{", *src, f"    const schema = z.array(z.any()).{call};",
                f"    const r = schema.safeParse([{arr}]);"]
        if not expected:
            body.append("    expect(r.success).toBe(true);")
        else:
            body += ["    expect(r.success).toBe(false);",
                     "    expect(r.success ? [] : r.error.issues).toMatchObject(" + json.dumps(expected) + ");"]
        body.append("});")
        return "\n".join(body)

    def test_edits(self, v):
        R = set(v.rules)
        rng = random.Random(v.seed * 101 + 7)
        pool = [self._case(rng, R) for _ in range(1500)]
        # drop cases whose items cannot be rendered distinctly (kept simple)
        tests = []
        for rid in v.rules:
            if rid == "types":
                continue
            drop = {rid} | {x for x in v.rules if rid in self.rule(x).needs}
            abl = R - drop
            if rid == "core":
                fails = [i for i, _ in pool if self.model(i, {}, R)][:4]
                passes = [i for i, _ in pool if not self.model(i, {}, R)][:3]
                chosen = [(i, {}) for i in fails + passes]
                for k, (i, o) in enumerate(chosen):
                    exp = self.model(i, o, {"core"})  # validity only: any custom issue(s)
                    tests.append(self._render_core(i, o, bool(exp), f"rule_core: c{k}"))
                continue
            disc = [(i, o) for i, o in pool if self.model(i, o, R) != self.model(i, o, abl)]
            disc.sort(key=lambda c: len(c[0]))
            if not disc:
                raise RuntimeError(f"no discriminating case for rule {rid} in {v.id}")
            okc = [(i, o) for i, o in pool if self.model(i, o, R) == self.model(i, o, abl) and self.model(i, o, R)]
            for k, (i, o) in enumerate(disc[:4] + okc[:1]):
                tests.append(self._render(i, o, self.model(i, o, R), f"rule_{rid}: c{k}", R))
        extra = []
        if "core" in R:
            extra.append('''test("rule_core: parsed output values are compared", () => {
    const schema = z.array(z.string().trim()).unique();
    expect(schema.safeParse([" a", "a"]).success).toBe(false);
    expect(schema.safeParse([" a", "b"]).success).toBe(true);
    expect(schema.safeParse([]).success).toBe(true);
    expect(schema.safeParse(["x"]).success).toBe(true);
});''')
            extra.append('''test("rule_core: SameValueZero examples from the specification", () => {
    const ok = (x: unknown[]) => z.array(z.any()).unique().safeParse(x).success;
    expect(ok([Number.NaN, Number.NaN])).toBe(false);
    expect(ok([0, -0])).toBe(false);
    expect(ok(["1", 1])).toBe(true);
    expect(ok([null, undefined])).toBe(true);
    expect(ok([{ a: 1 }, { a: 1 }])).toBe(true);
    const o = { a: 1 };
    expect(ok([o, o])).toBe(false);
    expect(ok([undefined, "a"])).toBe(true);
    expect(ok(["a", undefined])).toBe(true);
});''')
        if "perindex" in R:
            extra.append('''test("rule_perindex: nested path is prefixed", () => {
    const schema = z.object({ tags: z.array(z.string()).unique() });
    const r = schema.safeParse({ tags: ["a", "b", "a"] });
    expect(r.success).toBe(false);
    expect(r.success ? [] : r.error.issues.map((i) => i.path)).toEqual([["tags", 2]]);
});''')
        if "types" in R:
            extra.append('''test("rule_types: callback is typed with the element output type", () => {
    const ok = z.array(z.string()).unique({ by: (s) => s.length });
    expectTypeOf(ok).toEqualTypeOf<z.ZodArray<z.ZodString>>();
    // @ts-expect-error the callback receives a string, not a number
    z.array(z.string()).unique({ by: (s: number) => s });
    expect(ok.safeParse(["a", "bb"]).success).toBe(true);
    expect(ok.safeParse(["a", "b"]).success).toBe(false);
});''')
        head = ('import { expect, expectTypeOf, test } from "vitest";\nimport * as z from "zod/v4";\n\n')
        return [Edit(TEST, "create", head + "\n\n".join(tests + extra) + "\n", role="test")]

    def _render_core(self, items, opts, failing, name):
        refs = {}
        src = []
        for it in items:
            if isinstance(it, Obj) and it.ref and it.ref not in refs:
                refs[it.ref] = True
                src.append(f"    const {it.ref} = {js(it.struct)};")
        arr = ", ".join((it.ref if isinstance(it, Obj) and it.ref else js(it.struct)) if isinstance(it, Obj) else js(it) for it in items)
        body = [f"test({json.dumps(name)}, () => {{", *src, f"    const r = z.array(z.any()).unique().safeParse([{arr}]);"]
        if failing:
            body += ["    expect(r.success).toBe(false);",
                     "    expect(r.success ? [] : r.error.issues.every((i) => i.code === \"custom\" && i.message.length > 0)).toBe(true);"]
        else:
            body.append("    expect(r.success).toBe(true);")
        body.append("});")
        return "\n".join(body)
