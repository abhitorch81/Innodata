"""jsoncpp / Json::Value::merge: deep-merge of JSON documents.

Rule algebra (all toggleable): noover x nulldel x keepmismatch x deep(+depthlimit) x arrconcat(+arrunion) x selfmerge.
The implementation (C++) is generated from the rule set; expected results come from an INDEPENDENT functional
Python oracle (`model`) operating on plain dict/list/scalars, never from running the implementation."""
from __future__ import annotations
import copy
import json
from ..core import Recipe, Rule, Edit

FIX = "TaskMergeTest"


def kind(x):
    return "obj" if isinstance(x, dict) else "arr" if isinstance(x, list) else "sc"


def jeq(a, b):
    """Json::Value::operator== : types must match (bool != int != string), containers compare element-wise."""
    if kind(a) != kind(b):
        return False
    if kind(a) == "obj":
        return a.keys() == b.keys() and all(jeq(a[k], b[k]) for k in a)
    if kind(a) == "arr":
        return len(a) == len(b) and all(jeq(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


class JsoncppMerge(Recipe):
    repo = "jsoncpp"
    family = "merge"
    summary = "New `Json::Value::merge(patch, overwrite)` deep-merge member function"
    CORE = ("core",)
    ALL_RULES = [
        Rule("core", "Basic merge",
             "Add a public member function `Value& merge(const Value& patch, bool overwrite = true)` to "
             "`Json::Value` (declared in `include/json/value.h`, defined in `src/lib_json/json_value.cpp`). It "
             "merges `patch` into the receiver (`*this`), never modifies `patch`, copies (does not alias) whatever it "
             "takes from `patch`, and returns a reference to the receiver. If both the receiver and `patch` are "
             "objects, then for every member of `patch` the receiver ends up with a member of that name holding a "
             "copy of the patch's value (it is added when absent and replaced when present); receiver members that "
             "`patch` does not mention are untouched. If either of the two is not an object (null, bool, number, "
             "string or array), the receiver becomes a copy of `patch`. The `overwrite` argument only has an effect "
             "where a later requirement says so."),
        Rule("noover", "Fill-only mode",
             "Call `merge(patch, false)` with `overwrite == false` is a fill-only merge: if both values are objects, "
             "only members of `patch` whose name is absent from the receiver are added (as described for the basic "
             "merge); every member the receiver already has is left exactly as it is - not replaced, not removed, "
             "not merged into - and no recursion into nested objects takes place. If either value is not an object "
             "the receiver is left unchanged. With `overwrite == true` this requirement changes nothing."),
        Rule("nulldel", "Null deletes",
             "A member of the patch object whose value is null is never copied into the receiver: if the receiver "
             "has a member of that name, that member is removed, otherwise nothing happens. This concerns only the "
             "members of objects that are being merged member by member (the top-level objects, and nested objects "
             "when they are merged recursively). A patch value that is copied or assigned as a whole (for instance "
             "a nested object that replaces, or is added as, a receiver member) is copied verbatim, nulls inside "
             "it included. A null `patch` as a whole (not a member) is handled by the basic merge."),
        Rule("keepmismatch", "Keep on kind mismatch",
             "Classify values into three kinds: object, array, and scalar (null, bool, any number, string). When "
             "the receiver and the patch both have a member of the same name and those two member values are of "
             "different kinds, the receiver's value is kept unchanged. Values of the same kind are handled by the "
             "other requirements. This applies to members only, never to the receiver and patch as a whole."),
        Rule("deep", "Deep merge",
             "When the receiver and the patch both have a member of the same name and both member values are "
             "objects, those two objects are merged member by member, recursively, by the same rules, instead of "
             "the patch's object replacing the receiver's."),
        Rule("depthlimit", "Depth limit",
             "Recursive object merging stops at depth {depth}. Count depth as follows: members of the top-level "
             "objects are at depth 1, members of their members at depth 2, and so on. Two object-valued members at "
             "depth d are merged recursively only if d < {depth}; otherwise the patch's object replaces the "
             "receiver's (as in the basic merge).", needs=("deep",)),
        Rule("arrconcat", "Concatenate arrays",
             "If both values are arrays - the receiver and the patch as a whole, or two members of the same name - "
             "the receiver's array becomes its own elements followed by all elements of the patch's array, in "
             "order. Elements are copied as they are, never merged with each other."),
        Rule("arrunion", "Skip duplicate elements",
             "When concatenating arrays, an element of the patch array is appended only if no element currently in "
             "the receiver's array (including elements appended earlier in the same concatenation) is equal to "
             "it, where equal means `Json::Value::operator==`. The receiver's own elements are never removed or "
             "reordered, even when duplicated.", needs=("arrconcat",)),
        Rule("selfmerge", "Self merge",
             "Merging a value into itself, `v.merge(v)`, leaves `v` unchanged (whatever its content).",
             needs=("nulldel",)),
    ]

    def sample_params(self, rng, rules):
        return {"depth": rng.choice([2, 3])}

    def title(self, v): return "Add `Json::Value::merge` (deep merge of JSON documents)"

    def preamble(self, v):
        return ("JsonCpp can build and edit `Json::Value` trees but offers no way to overlay one document on "
                "another (configuration defaults, patches, ...). Add the member function described below. "
                "If two requirements could both apply to the same pair of values, the one listed first takes "
                "precedence. Object member order is not significant (`Json::Value` keeps members sorted).")

    # ------------------------------------------------------------------ oracle (independent, functional)
    def model(self, dst, src, R, P, mode="default"):
        if mode == "self" and "selfmerge" in R:
            return copy.deepcopy(dst)
        fill_only = mode == "nooverwrite"
        src = copy.deepcopy(src)

        def cat(a, b):
            out = list(a)
            for e in b:
                if "arrunion" in R and any(jeq(e, x) for x in out):
                    continue
                out.append(e)
            return out

        def go(d, s, depth):
            if kind(d) == "obj" and kind(s) == "obj":
                out = dict(d)
                for k, sv in s.items():
                    if "noover" in R and fill_only and k in out:
                        continue
                    if "nulldel" in R and sv is None:
                        out.pop(k, None)
                        continue
                    if k not in out:
                        out[k] = sv
                        continue
                    dv = out[k]
                    if "keepmismatch" in R and kind(dv) != kind(sv):
                        continue
                    if "deep" in R and kind(dv) == kind(sv) == "obj" and \
                            ("depthlimit" not in R or depth + 1 < P["depth"]):
                        out[k] = go(dv, sv, depth + 1)
                        continue
                    if "arrconcat" in R and kind(dv) == kind(sv) == "arr":
                        out[k] = cat(dv, sv)
                        continue
                    out[k] = sv
                return out
            if "noover" in R and fill_only:
                return d
            if "arrconcat" in R and kind(d) == kind(s) == "arr":
                return cat(d, s)
            return s

        return go(copy.deepcopy(dst), src, 0)

    # ------------------------------------------------------------------ implementation
    def impl_edits(self, v, rules):
        has = rules.__contains__
        D = v.params["depth"]
        L = []
        a = L.append
        a("namespace {")
        if has("keepmismatch"):
            a("enum MergeKind { kMergeObject, kMergeArray, kMergeScalar };")
            a("MergeKind mergeKindOf(const Value& value) {")
            a("  if (value.isObject())")
            a("    return kMergeObject;")
            a("  return value.isArray() ? kMergeArray : kMergeScalar;")
            a("}")
            a("")
        if has("arrconcat"):
            a("void mergeArrays(Value& dst, const Value& src) {")
            a("  const ArrayIndex count = src.size();")
            a("  for (ArrayIndex i = 0; i < count; ++i) {")
            a("    const Value& element = src[i];")
            if has("arrunion"):
                a("    bool seen = false;")
                a("    for (ArrayIndex j = 0; j < dst.size() && !seen; ++j) {")
                a("      seen = (dst[j] == element);")
                a("    }")
                a("    if (seen)")
                a("      continue;")
            a("    dst.append(element);")
            a("  }")
            a("}")
            a("")
        sig = ("int depth, " if has("depthlimit") else "") + ("bool overwrite, " if has("noover") else "")
        arg = ("depth + 1, " if has("depthlimit") else "") + ("overwrite, " if has("noover") else "")
        top = ("0, " if has("depthlimit") else "") + ("overwrite, " if has("noover") else "")
        a(f"void mergeValues(Value& dst, const Value& src{', ' + sig[:-2] if sig else ''}) {{")
        a("  if (dst.isObject() && src.isObject()) {")
        a("    const Value::Members names = src.getMemberNames();")
        a("    for (const String& name : names) {")
        a("      const Value& patch = src[name];")
        if has("noover"):
            a("      if (!overwrite && dst.isMember(name))")
            a("        continue;")
        if has("nulldel"):
            a("      if (patch.isNull()) {")
            a("        dst.removeMember(name);")
            a("        continue;")
            a("      }")
        a("      if (!dst.isMember(name)) {")
        a("        dst[name] = patch;")
        a("        continue;")
        a("      }")
        a("      Value& current = dst[name];")
        if has("keepmismatch"):
            a("      if (mergeKindOf(current) != mergeKindOf(patch))")
            a("        continue;")
        if has("deep"):
            cond = "current.isObject() && patch.isObject()"
            if has("depthlimit"):
                cond += f" && depth + 1 < {D}"
            a(f"      if ({cond}) {{")
            a(f"        mergeValues(current, patch{', ' + arg[:-2] if arg else ''});")
            a("        continue;")
            a("      }")
        if has("arrconcat"):
            a("      if (current.isArray() && patch.isArray()) {")
            a("        mergeArrays(current, patch);")
            a("        continue;")
            a("      }")
        a("      current = patch;")
        a("    }")
        a("    return;")
        a("  }")
        if has("noover"):
            a("  if (!overwrite)")
            a("    return;")
        if has("arrconcat"):
            a("  if (dst.isArray() && src.isArray()) {")
            a("    mergeArrays(dst, src);")
            a("    return;")
            a("  }")
        a("  dst = src;")
        a("}")
        a("} // namespace")
        a("")
        a("Value& Value::merge(const Value& patch, bool overwrite) {")
        if has("selfmerge"):
            a("  if (&patch == this)")
            a("    return *this;")
        if not has("noover"):
            a("  (void)overwrite;")
        a(f"  mergeValues(*this, patch{', ' + top[:-2] if top else ''});")
        a("  return *this;")
        a("}")
        a("")
        cpp = "\n".join(L) + "\n"
        decl = ("  /// \\brief Merge `patch` into this value (objects merge member-wise); see the\n"
                "  /// documentation of each merge mode in the task description.\n"
                "  Value& merge(const Value& patch, bool overwrite = true);\n")
        return [
            Edit("include/json/value.h", "insert_after", "\n" + decl, anchor="  Value& append(Value&& value);\n"),
            Edit("src/lib_json/json_value.cpp", "insert_before", cpp,
                 anchor="bool Value::insert(ArrayIndex index, const Value& newValue) {"),
        ]

    # ------------------------------------------------------------------ tests
    def feature_test_paths(self, v):
        return ["src/test_lib_json/main.cpp"]

    POOLS = {
        "core": [({"a": 1}, {"b": 2}), ({"a": 1, "b": 2}, {"a": 3}), ({"a": 1}, {}), ({}, {"a": 1}),
                 (5, {"a": 1}), ({"a": 1}, 5), ("x", "y"), (None, {"a": 1}), ({"a": 1}, [1, 2]),
                 ([1, 2], {"a": 1}), (1, [3]), ({"a": {"x": 1}}, {"a": {"x": 2}}),
                 ({"a": 1, "b": [1, 2]}, {"c": "s", "a": True}), ({"a": 1}, None), ([1], "s"),
                 ({"a": [1, 2], "z": 0}, {"a": 7, "y": 9})],
        "noover": [({"a": 1}, {"a": 2, "b": 3}), ({"a": {"x": 1}}, {"a": {"y": 2}}), ({"a": [1]}, {"a": [2], "b": [3]}),
                   (5, {"a": 1}), ({"a": 1}, {"b": {"c": 2}}), ({}, {"a": 1}), ({"a": 1}, {"a": None}),
                   ({"a": {"x": 1}}, {"a": {"x": 2, "y": 3}, "b": 1}), ([1], [2]), ({"a": 1}, 7)],
        "nulldel": [({"a": 1, "b": 2}, {"a": None}), ({"a": 1}, {"b": None}), ({"a": 1}, {"a": None, "b": 2}),
                    ({"a": {"x": 1, "y": 2}}, {"a": {"x": None}}), ({"a": {"x": 1}}, {"b": {"y": None}}),
                    ({"a": {"x": 1}}, {"a": None}), ({"a": [1]}, {"a": [None]}), ({"a": None}, {"a": None}),
                    ({"a": 1, "b": {"c": 2}}, {"b": None, "c": 3})],
        "keepmismatch": [({"a": {"x": 1}}, {"a": [1]}), ({"a": [1]}, {"a": "s"}), ({"a": 1}, {"a": {"x": 1}}),
                         ({"a": 1}, {"a": "s"}), ({"a": None}, {"a": {"x": 1}}), ({"a": {"x": 1}}, {"a": None}),
                         ({"a": "s"}, {"a": [1], "b": 2}), ({"a": [1]}, {"a": [2]}), ({"a": 1}, {"a": 2})],
        "deep": [({"a": {"x": 1, "y": 2}}, {"a": {"y": 3, "z": 4}}), ({"a": {"b": {"c": 1}}}, {"a": {"b": {"d": 2}}}),
                 ({"a": {"x": 1}}, {"b": {"y": 2}}), ({"a": {"x": 1}}, {"a": 5}), ({"a": 5}, {"a": {"x": 1}}),
                 ({"a": {"x": {"y": {"z": 1, "w": 0}}}}, {"a": {"x": {"y": {"z": 2}}}}), ({"a": {}}, {"a": {"k": 1}}),
                 ({"a": {"x": 1}}, {"a": {}}), ({"a": {"x": 1}}, {"a": [1]})],
        "depthlimit": [({"a": {"b": {"c": {"d": 1, "e": 2}}}}, {"a": {"b": {"c": {"d": 9, "f": 3}}}}),
                       ({"a": {"b": {"x": 1}}}, {"a": {"b": {"y": 2}}}),
                       ({"a": {"x": 1, "y": 2}}, {"a": {"y": 3}}),
                       ({"a": {"b": {"c": {"d": {"e": 1, "f": 1}}}}}, {"a": {"b": {"c": {"d": {"e": 2}}}}}),
                       ({"k": 1, "a": {"b": {"c": 1, "d": 2}, "e": 3}}, {"a": {"b": {"c": 5}, "f": 4}})],
        "arrconcat": [({"a": [1, 2]}, {"a": [3]}), ([1], [2, 3]), ({"a": [1]}, {"a": []}), ({"a": []}, {"a": [1]}),
                      ({"a": [1]}, {"a": {"x": 1}}), ({"a": [1, 2]}, {"b": [3]}), ({"a": {"b": [1]}}, {"a": {"b": [2]}}),
                      ({"a": [[1], {"x": 1}]}, {"a": [[2]]}), ([], [1]), ({"a": [1]}, {"a": "s"})],
        "arrunion": [({"a": [1, 2]}, {"a": [2, 3]}), ({"a": [1]}, {"a": [3, 3]}), ({"a": [1, 1]}, {"a": [1]}),
                     ({"a": [{"x": 1}]}, {"a": [{"x": 1}, {"x": 2}]}), ({"a": ["1"]}, {"a": [1]}),
                     ([1, 2], [2, 3]), ({"a": [True]}, {"a": [1]}), ({"a": [[1]]}, {"a": [[1], [2]]}),
                     ({"a": [1]}, {"a": [2]}), ({"a": []}, {"a": [4, 4, 5]})],
        "selfmerge": [{"a": [1, 2], "b": {"c": [3]}}, {"a": None, "b": 1}, [1, 2, 3], {"a": {"b": None}},
                      {"x": 1}, 5, {"a": [None, 1]}, {"a": {"b": [1, 2]}}],
    }

    def _cases(self, rid, R, P):
        full = set(R)
        drop = {rid} | {x for x in R if rid in self.rule(x).needs}
        abl = full - drop
        mode = "nooverwrite" if rid == "noover" else "self" if rid == "selfmerge" else "default"
        disc, same = [], []
        for item in self.POOLS[rid]:
            d, p = (item, item) if rid == "selfmerge" else item
            if rid == "core":
                e1 = self.model(d, p, full, P)
                if e1 == self.model(d, p, {"core"}, P) and not (e1 is None):
                    same.append((d, p, e1, mode))
                elif e1 is None and self.model(d, p, {"core"}, P) is None:
                    same.append((d, p, e1, mode))
                continue
            e1, e0 = self.model(d, p, full, P, mode), self.model(d, p, abl, P, mode)
            (disc if e1 != e0 else same).append((d, p, e1, mode))
        if rid == "core":
            return same
        if not disc:
            raise RuntimeError(f"rule {rid}: no discriminating case in pool")
        return disc + same[:2]

    def test_edits(self, v):
        R, P = set(v.rules), v.params
        J = lambda x: json.dumps(x, separators=(",", ":"), sort_keys=True)
        L = [
            "", "// ---- task tests: Json::Value::merge (generated; one `rule_<id>_c<n>` test per case) ----",
            f"struct {FIX} : JsonTest::TestCase {{",
            "  static Json::Value parse(const std::string& text) {",
            "    Json::CharReaderBuilder builder;",
            "    CharReaderPtr reader(builder.newCharReader());",
            "    Json::Value value;",
            "    Json::String errs;",
            "    reader->parse(text.data(), text.data() + text.size(), &value, &errs);",
            "    return value;",
            "  }",
            "  static Json::String compact(const Json::Value& value) {",
            "    Json::StreamWriterBuilder builder;",
            "    builder[\"indentation\"] = \"\";",
            "    return Json::writeString(builder, value);",
            "  }",
            "  // mode 0: merge(patch)   1: merge(patch, false)   2: v.merge(v)",
            "  void check(const std::string& dst, const std::string& patch, const std::string& expected, int mode) {",
            "    Json::Value receiver = parse(dst);",
            "    const Json::Value patchValue = parse(patch);",
            "    const Json::Value want = parse(expected);",
            "    Json::Value* returned = nullptr;",
            "    try {",
            "      if (mode == 2)",
            "        returned = &receiver.merge(receiver);",
            "      else if (mode == 1)",
            "        returned = &receiver.merge(patchValue, false);",
            "      else",
            "        returned = &receiver.merge(patchValue);",
            "    } catch (const std::exception&) {",
            "      JSONTEST_ASSERT(false);",
            "      return;",
            "    }",
            "    JSONTEST_ASSERT(returned == &receiver);",
            "    if (mode != 2) {",
            "      JSONTEST_ASSERT_STRING_EQUAL(compact(parse(patch)), compact(patchValue));",
            "    }",
            "    JSONTEST_ASSERT_STRING_EQUAL(compact(want), compact(receiver));",
            "  }",
            "};", "",
        ]
        for rid in v.rules:
            for i, (d, p, e, mode) in enumerate(self._cases(rid, R, P), 1):
                m = {"default": 0, "nooverwrite": 1, "self": 2}[mode]
                L += [f"JSONTEST_FIXTURE_LOCAL({FIX}, rule_{rid}_c{i}) {{",
                      f"  check(R\"J({J(d)})J\", R\"J({J(p)})J\", R\"J({J(e)})J\", {m});", "}", ""]
        L += [f"JSONTEST_FIXTURE_LOCAL({FIX}, rule_core_independent) {{",
              "  // the receiver must not alias the patch: editing the receiver afterwards leaves the patch alone",
              "  Json::Value receiver = parse(\"{\\\"a\\\":1}\");",
              "  const Json::Value patch = parse(\"{\\\"b\\\":{\\\"c\\\":[1,2]}}\");",
              "  receiver.merge(patch);",
              "  receiver[\"b\"][\"c\"].append(3);",
              "  receiver[\"b\"][\"d\"] = true;",
              "  JSONTEST_ASSERT_STRING_EQUAL(std::string(\"{\\\"b\\\":{\\\"c\\\":[1,2]}}\"), compact(patch));",
              "}", ""]
        return [Edit("src/test_lib_json/main.cpp", "append", "\n".join(L), role="test")]
