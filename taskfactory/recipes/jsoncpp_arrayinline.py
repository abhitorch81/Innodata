"""jsoncpp / StreamWriterBuilder "arrayInlineLimit": short scalar arrays printed on one line in pretty mode.

Modifies EXISTING writer code (json_writer.cpp). Rules: emptyelem, nestedarr, totalcount, noroot, maxwidth,
commentguard, strictvalue (+ core, with a behavioural `pad` parameter). Expected output comes from an independent
Python re-implementation of the pretty writer (`model`), checked against the unmodified library for limit 0."""
from __future__ import annotations
import json
from ..core import Recipe, Rule, Edit

FIX = "TaskInlineTest"


class Cm:
    """value carrying a 'comment after on same line'"""
    def __init__(self, v, c): self.v, self.c = v, c


def un(x): return (x.v, x.c) if isinstance(x, Cm) else (x, None)
def kind(v): return "obj" if isinstance(v, dict) else "arr" if isinstance(v, list) else "sc"
def scal(v): return "null" if v is None else "true" if v is True else "false" if v is False else json.dumps(v)


def strip(x, path, found):
    v, c = un(x)
    if c is not None:
        found.append((list(path), c))
    if isinstance(v, dict):
        return {k: strip(e, path + [k], found) for k, e in v.items()}
    if isinstance(v, list):
        return [strip(e, path + [i], found) for i, e in enumerate(v)]
    return v


class JsoncppArrayInline(Recipe):
    repo = "jsoncpp"
    family = "arrayinline"
    summary = "New StreamWriterBuilder setting `arrayInlineLimit` (short scalar arrays on one line)"
    CORE = ("core",)
    ALL_RULES = [
        Rule("core", "The `arrayInlineLimit` setting",
             "Add a `StreamWriterBuilder` setting `\"arrayInlineLimit\"` (an unsigned integer). `setDefaults` must "
             "set it to `0` (so `settings_[\"arrayInlineLimit\"]` is `0` on a fresh builder) and `validate()` must "
             "accept the key as a known setting. With value `0`, or when `\"indentation\"` is the empty string, the "
             "output is byte-for-byte what the writer produced before this change. Otherwise, with limit N > 0, a "
             "non-empty array that has at most N elements, every element being a simple value (null, bool, number "
             "or string), is written on a single line as {inline_form}, elements separated by `, ` and each "
             "formatted exactly as it would be otherwise. This holds for both `commentStyle` values. A single-line "
             "array follows its member name and colon directly (`\"key\" : [1, 2]`), appears on its own indented "
             "line when it is an element of a multi-line array, and starts the output when it is the root. Every "
             "array that is not written on a single line by these requirements is written exactly as before. "
             "When `commentStyle` is `\"None\"`, only arrays that qualify for a single line are tested."),
        Rule("emptyelem", "Empty containers count as simple",
             "An empty array (`[]`) or empty object (`{{}}`) element also counts as a simple value for the purpose of "
             "the single-line condition, and is written `[]` / `{{}}` inside the line. Non-empty objects never count."),
        Rule("nestedarr", "Nested single-line arrays",
             "A non-empty array element counts as a simple value if that array itself qualifies for a single line "
             "under these requirements (including the element-count limit); it is then written inline inside the "
             "outer line, in the same form. Arrays that do not qualify disqualify their parent."),
        Rule("totalcount", "Limit counts leaves",
             "The limit N bounds the total number of simple values (empty containers included, when they count) "
             "found in the array at any depth, instead of only its direct elements. Every array, nested ones "
             "included, is judged by the leaves it contains.", needs=("nestedarr",)),
        Rule("noroot", "Root array is exempt",
             "An array that is the root value of the document is never written on a single line; it is written "
             "exactly as before. Arrays below the root are unaffected."),
        Rule("maxwidth", "Width cap",
             "An array is written on a single line only if its single-line text, from `[` through `]`, is at most "
             "{width} characters long (strings count as written, quotes included). Otherwise it is written as before."),
        Rule("commentguard", "Comments keep arrays expanded",
             "When `commentStyle` is `\"All\"`, an array with an element that has a comment attached to it "
             "(placement does not matter) is not written on a single line, so that the comment is preserved; it is "
             "written as before. A comment on the array itself does not matter. With `commentStyle` `\"None\"` "
             "comments are not written and have no effect."),
        Rule("strictvalue", "Strict setting validation",
             "`newStreamWriter()` throws a `std::exception` unless `\"arrayInlineLimit\"` is an integer value "
             "(`Json::intValue` or `Json::uintValue`) that is not negative. Reals (even whole ones), bools and "
             "strings are rejected. A setting that is missing behaves as `0`."),
    ]

    def sample_params(self, rng, rules):
        return {"pad": rng.choice([False, True]), "width": rng.choice([16, 22, 28])}

    def title(self, v): return "Add the `arrayInlineLimit` StreamWriterBuilder setting"

    def preamble(self, v):
        return ("In pretty mode `StreamWriterBuilder` writes every array one element per line, which makes lists of "
                "small numbers very tall. Add an opt-in setting that prints short arrays on one line. "
                "Examples use indentation of two spaces. The implementation belongs in "
                "`src/lib_json/json_writer.cpp` (document the setting in `include/json/writer.h`).")

    def _form(self, P): return "`[ 1, 2 ]` (a space after `[` and before `]`)" if P["pad"] else "`[1, 2]` (no space inside the brackets)"

    def requirements_md(self, v):
        v2 = type(v)(v.family, v.seed, v.rules, dict(v.params, inline_form=self._form(v.params)))
        return super().requirements_md(v2)

    # ------------------------------------------------------------------ oracle
    def model(self, value, R, P, cfg):
        N, I, cs = cfg["limit"], cfg["indent"], cfg["cs"]
        if I == "":
            def comp(x):
                v, _ = un(x)
                if isinstance(v, dict):
                    return "{" + ",".join(json.dumps(k) + ":" + comp(v[k]) for k in sorted(v)) + "}"
                if isinstance(v, list):
                    return "[" + ",".join(comp(e) for e in v) + "]"
                return scal(v)
            return comp(value)

        def line(arr, root):
            """-> (text, leaves) if arr is written on a single line, else None"""
            if N == 0 or (root and "noroot" in R) or not arr:
                return None
            if "totalcount" not in R and len(arr) > N:
                return None
            parts, leaves = [], 0
            for e in arr:
                ev, c = un(e)
                if c is not None and "commentguard" in R and cs == "All":
                    return None
                if kind(ev) == "sc":
                    parts.append(scal(ev)); leaves += 1
                elif not ev and "emptyelem" in R:
                    parts.append("[]" if isinstance(ev, list) else "{}"); leaves += 1
                elif kind(ev) == "arr" and ev and "nestedarr" in R:
                    sub = line(ev, False)
                    if sub is None:
                        return None
                    parts.append(sub[0]); leaves += sub[1]
                else:
                    return None
            if "totalcount" in R and leaves > N:
                return None
            text = ("[ " + ", ".join(parts) + " ]") if P["pad"] else ("[" + ", ".join(parts) + "]")
            if "maxwidth" in R and len(text) > P["width"]:
                return None
            return text, leaves

        def emit(x, ind, root):
            """-> (text, multi): `multi` texts already start with their newline+indent lead (except root)"""
            v, _ = un(x)
            if kind(v) == "sc":
                return scal(v), False
            if not v:
                return ("[]" if isinstance(v, list) else "{}"), False
            if isinstance(v, list):
                one = line(v, root)
                if one:
                    return one[0], False
            ind2 = ind + I
            lead = "" if root else "\n" + ind
            if isinstance(v, list):
                items = [(None, e) for e in v]; o, c = "[", "]"
            else:
                items = [(k, v[k]) for k in sorted(v)]; o, c = "{", "}"
            out = lead + o
            for n, (k, e) in enumerate(items):
                t, multi = emit(e, ind2, False)
                head = "" if k is None else json.dumps(k) + " : "
                body = t if (multi and k is None) else "\n" + ind2 + head + t
                out += body
                if n + 1 < len(items):
                    out += ","
                _, com = un(e)
                if com is not None and cs == "All":
                    out += " " + com
            return out + "\n" + ind + c, True

        return emit(value, "", True)[0]

    # ------------------------------------------------------------------ implementation
    def impl_edits(self, v, rules):
        has, P = rules.__contains__, v.params
        W = P["width"]
        o, c = ("\"[ \"", "\" ]\"") if P["pad"] else ("\"[\"", "\"]\"")
        H = []
        a = H.append
        a("void BuiltStyledStreamWriter::configureInline(unsigned int limit) { inlineLimit_ = limit; }")
        a("")
        a("String BuiltStyledStreamWriter::inlineScalarText(Value const& value) {")
        a("  ChildValues saved;")
        a("  saved.swap(childValues_);")
        a("  const bool savedAdd = addChildValues_;")
        a("  addChildValues_ = true;")
        a("  writeValue(value);")
        a("  String text = childValues_.empty() ? String() : childValues_.back();")
        a("  childValues_.swap(saved);")
        a("  addChildValues_ = savedAdd;")
        a("  return text;")
        a("}")
        a("")
        a("bool BuiltStyledStreamWriter::buildInlineArray(Value const& value, String& out,")
        a("                                               unsigned int& leaves) {")
        a("  ArrayIndex const size = value.size();")
        a("  if (size == 0)")
        a("    return false;")
        if not has("totalcount"):
            a("  if (size > inlineLimit_)")
            a("    return false;")
        if has("commentguard"):
            a("  if (cs_ == CommentStyle::All) {")
            a("    for (ArrayIndex index = 0; index < size; ++index) {")
            a("      if (hasCommentForValue(value[index]))")
            a("        return false;")
            a("    }")
            a("  }")
        a(f"  String text = {o};")
        a("  unsigned int own = 0;")
        a("  for (ArrayIndex index = 0; index < size; ++index) {")
        a("    Value const& child = value[index];")
        a("    if (index > 0)")
        a("      text += \", \";")
        a("    if (child.isArray() || child.isObject()) {")
        if has("emptyelem"):
            a("      if (child.empty()) {")
            a("        text += child.isArray() ? \"[]\" : \"{}\";")
            a("        ++own;")
            a("        continue;")
            a("      }")
        if has("nestedarr"):
            a("      if (child.isArray()) {")
            a("        String inner;")
            a("        unsigned int innerLeaves = 0;")
            a("        if (!buildInlineArray(child, inner, innerLeaves))")
            a("          return false;")
            a("        text += inner;")
            a("        own += innerLeaves;")
            a("        continue;")
            a("      }")
        a("      return false;")
        a("    }")
        a("    text += inlineScalarText(child);")
        a("    ++own;")
        a("  }")
        if has("totalcount"):
            a("  if (own > inlineLimit_)")
            a("    return false;")
        a(f"  text += {c};")
        if has("maxwidth"):
            a(f"  if (text.size() > {W})")
            a("    return false;")
        a("  out = text;")
        a("  leaves = own;")
        a("  return true;")
        a("}")
        a("")
        a("bool BuiltStyledStreamWriter::inlineArrayText(Value const& value, String& out) {")
        a("  if (inlineLimit_ == 0 || indentation_.empty())")
        a("    return false;")
        if has("noroot"):
            a("  if (&value == rootValue_)")
            a("    return false;")
        a("  unsigned int leaves = 0;")
        a("  return buildInlineArray(value, out, leaves);")
        a("}")
        a("")
        if has("strictvalue"):
            parse = ('  const Value& limitSetting = settings_["arrayInlineLimit"];\n'
                     '  unsigned int inlineLimit = 0;\n'
                     '  if (limitSetting.type() == intValue || limitSetting.type() == uintValue) {\n'
                     '    if (limitSetting.type() == intValue && limitSetting.asInt64() < 0)\n'
                     '      throwRuntimeError("arrayInlineLimit must not be negative");\n'
                     '    inlineLimit = limitSetting.asUInt();\n'
                     '  } else if (!limitSetting.isNull()) {\n'
                     '    throwRuntimeError("arrayInlineLimit must be an integer");\n'
                     '  }\n')
        else:
            parse = '  const unsigned int inlineLimit = settings_["arrayInlineLimit"].asUInt();\n'
        newret = (parse + "  BuiltStyledStreamWriter* writer = new BuiltStyledStreamWriter(\n"
                  "      indentation, cs, colonSymbol, nullSymbol, endingLineFeedSymbol, usf, emitUTF8, pre,\n"
                  "      precisionType);\n  writer->configureInline(inlineLimit);\n  return writer;")
        decl = ("  int write(Value const& root, OStream* sout) override;\n"
                "  void configureInline(unsigned int limit);\n")
        priv = ("  void writeArrayValue(Value const& value);\n"
                "  bool inlineArrayText(Value const& value, String& out);\n"
                "  bool buildInlineArray(Value const& value, String& out, unsigned int& leaves);\n"
                "  String inlineScalarText(Value const& value);\n")
        return [
            Edit("src/lib_json/json_writer.cpp", "replace", decl,
                 anchor="  int write(Value const& root, OStream* sout) override;\n"),
            Edit("src/lib_json/json_writer.cpp", "replace",
                 "  PrecisionType precisionType_;\n  unsigned int inlineLimit_ = 0;\n  Value const* rootValue_ = nullptr;\n};",
                 anchor="  PrecisionType precisionType_;\n};"),
            Edit("src/lib_json/json_writer.cpp", "replace",
                 "  indented_ = true;\n  indentString_.clear();\n  rootValue_ = &root;\n  writeCommentBeforeValue(root);",
                 anchor="  indented_ = true;\n  indentString_.clear();\n  writeCommentBeforeValue(root);"),
            Edit("src/lib_json/json_writer.cpp", "replace", priv,
                 anchor="  void writeArrayValue(Value const& value);\n"),
            Edit("src/lib_json/json_writer.cpp", "insert_before",
                 "    String inlineText;\n    if (inlineArrayText(value, inlineText)) {\n      pushValue(inlineText);\n      return;\n    }\n",
                 anchor="    bool isMultiLine = (cs_ == CommentStyle::All) || isMultilineArray(value);"),
            Edit("src/lib_json/json_writer.cpp", "insert_before", "\n".join(H),
                 anchor="bool BuiltStyledStreamWriter::isMultilineArray(Value const& value) {"),
            Edit("src/lib_json/json_writer.cpp", "replace", newret,
                 anchor="  return new BuiltStyledStreamWriter(indentation, cs, colonSymbol, nullSymbol,\n"
                        "                                     endingLineFeedSymbol, usf, emitUTF8, pre,\n"
                        "                                     precisionType);"),
            Edit("src/lib_json/json_writer.cpp", "replace", "      \"precisionType\",\n      \"arrayInlineLimit\",\n  };",
                 anchor="      \"precisionType\",\n  };"),
            Edit("src/lib_json/json_writer.cpp", "insert_after", "  (*settings)[\"arrayInlineLimit\"] = 0;\n",
                 anchor="  (*settings)[\"precisionType\"] = \"significant\";\n"),
            Edit("include/json/writer.h", "insert_after",
                 "   *  - \"arrayInlineLimit\": unsigned int (default 0 = off)\n"
                 "   *  - In pretty mode, short arrays of simple values are written on one line.\n",
                 anchor="   *  - If true, outputs raw UTF8 strings instead of escaping them.\n"),
        ]

    # ------------------------------------------------------------------ tests
    def feature_test_paths(self, v):
        return ["src/test_lib_json/main.cpp"]

    def _pool(self, rid, P):
        W = P["width"]
        def arr_of_width(target):
            # three strings; total single-line text length == target for the variant's padding
            over = (4 if P["pad"] else 2) + 2 * 2
            budget = target - over - 3 * 2  # minus quotes
            base = budget // 3
            lens = [base + budget - 3 * base, base, base]
            return ["x" * n for n in lens]
        S = "  "
        pools = {
            "core": [({"a": [1, 2, 3]}, 3), ({"a": [1, 2, 3, 4]}, 3), ({"a": []}, 3), ({"a": [1, "x", None, True]}, 4),
                     ({"a": [1, 2, 3]}, 0), ({"a": [[1], [2]]}, 3), ({"a": [{"x": 1}]}, 3), ({"k": {"a": [1, 2]}, "z": [5]}, 3),
                     ({"a": [1, 2]}, 3, "", "All"), ({"a": [1, 2]}, 3, S, "None"), ({"a": [1, 2], "b": 7}, 2),
                     ({"a": [1, 2, 3]}, 2), ({"o": {"p": {"q": ["a", "b"]}}}, 5), ([{"a": [1]}, 2], 4)],
            "noroot": [([1, 2, 3], 3), ({"a": [1, 2]}, 3), ([1, 2], 5, S, "None"), ([[1], 2], 3), ({"a": [[1, 2]]}, 3)],
            "emptyelem": [({"a": [1, [], {}]}, 3), ({"a": [[], []]}, 3), ({"a": [{}]}, 1), ({"a": [1, {"x": 1}]}, 3),
                          ({"a": [1, 2, []]}, 2), ({"a": [[]]}, 1)],
            "nestedarr": [({"a": [[1, 2], [3]]}, 2), ({"a": [[1, 2, 3], [4]]}, 2), ({"a": [[[1]]]}, 1),
                          ({"a": [[1, {"x": 1}]]}, 2), ({"a": [1, [2, 3]]}, 2), ({"a": [[1], [2]]}, 2)],
            "totalcount": [({"a": [[1, 2], [3, 4]]}, 4), ({"a": [[1, 2], [3, 4]]}, 3), ({"a": [[1, 2, 3], [4]]}, 3),
                           ({"a": [[1], [2], [3]]}, 3), ({"a": [[1], [2], [3]]}, 2), ({"a": [1, [2, 3]]}, 3)],
            "maxwidth": [({"a": arr_of_width(W)}, 10), ({"a": arr_of_width(W + 1)}, 10), ({"a": arr_of_width(W - 1)}, 10),
                         ({"a": [1, 2, 3]}, 10), ({"a": arr_of_width(W + 7)}, 10)],
            "commentguard": [({"a": [1, Cm(2, "// c"), 3]}, 3), ({"a": [1, Cm(2, "// c"), 3]}, 3, S, "None"),
                             ({"a": Cm([1, 2], "// c"), "b": 1}, 3), ({"a": [Cm(1, "// c")], "b": [2]}, 3),
                             ({"a": [1, 2], "b": Cm(3, "// c")}, 3)],
        }
        return pools[rid]

    def _cases(self, rid, R, P):
        full = set(R)
        drop = {rid} | {x for x in R if rid in self.rule(x).needs}
        abl = full - drop
        disc, same = [], []
        for item in self._pool(rid, P):
            val, lim = item[0], item[1]
            ind = item[2] if len(item) > 2 else "  "
            cs = item[3] if len(item) > 3 else "All"
            cfg = dict(limit=lim, indent=ind, cs=cs)
            if cs == "None" and not self._all_eligible(val, full, P, cfg):
                continue
            e1 = self.model(val, full, P, cfg)
            if rid == "core" and e1 == self.model(val, full, P, dict(cfg, limit=0)):
                continue  # identical to base-commit output: would pass before the change (S1 requires fail-to-pass)
            if rid == "core":
                if e1 == self.model(val, {"core"}, P, cfg):
                    same.append((val, cfg, e1))
                continue
            (disc if e1 != self.model(val, abl, P, cfg) else same).append((val, cfg, e1))
        if rid == "core":
            return same
        if not disc:
            raise RuntimeError(f"rule {rid}: no discriminating case in pool")
        return disc + same[:2]

    def _all_eligible(self, val, R, P, cfg):
        """cs=None legacy fallback is out of scope: every non-empty array must render inline"""
        def walk(x):
            v, _ = un(x)
            if isinstance(v, list):
                if v and not self._inline_text(v, R, P, cfg):
                    return False
                return all(walk(e) for e in v)
            if isinstance(v, dict):
                return all(walk(e) for e in v.values())
            return True
        return walk(val)

    def _inline_text(self, arr, R, P, cfg):
        out = self.model(arr, R, P, cfg)
        return "\n" not in out

    def test_edits(self, v):
        R, P = set(v.rules), v.params
        L = ["", "// ---- task tests: StreamWriterBuilder arrayInlineLimit (generated) ----",
             f"struct {FIX} : JsonTest::TestCase {{",
             "  static Json::Value parse(const std::string& text) {",
             "    Json::CharReaderBuilder builder;",
             "    CharReaderPtr reader(builder.newCharReader());",
             "    Json::Value value;",
             "    Json::String errs;",
             "    reader->parse(text.data(), text.data() + text.size(), &value, &errs);",
             "    return value;",
             "  }",
             "  void expectRender(const Json::Value& value, int limit, const char* indent, const char* style,",
             "                    const std::string& expected) {",
             "    Json::StreamWriterBuilder builder;",
             "    builder[\"indentation\"] = indent;",
             "    builder[\"commentStyle\"] = style;",
             "    builder[\"arrayInlineLimit\"] = limit;",
             "    Json::String actual;",
             "    try {",
             "      actual = Json::writeString(builder, value);",
             "    } catch (const std::exception&) {",
             "      JSONTEST_ASSERT(false);",
             "      return;",
             "    }",
             "    JSONTEST_ASSERT_STRING_EQUAL(expected, actual);",
             "  }",
             "};", ""]
        J = lambda x: json.dumps(x, separators=(",", ":"), sort_keys=True)
        for rid in v.rules:
            if rid == "strictvalue":
                continue
            for i, (val, cfg, exp) in enumerate(self._cases(rid, R, P), 1):
                found = []
                plain = strip(val, [], found)
                L.append(f"JSONTEST_FIXTURE_LOCAL({FIX}, rule_{rid}_c{i}) {{")
                L.append(f"  Json::Value value = parse(R\"J({J(plain)})J\");")
                for path, com in found:
                    acc = "".join(f"[{k}]" if isinstance(k, int) else f"[\"{k}\"]" for k in path)
                    L.append(f"  value{acc}.setComment(std::string(\"{com}\"), Json::commentAfterOnSameLine);")
                L.append(f"  expectRender(value, {cfg['limit']}, \"{cfg['indent']}\", \"{cfg['cs']}\", R\"J({exp})J\");")
                L += ["}", ""]
        L += [f"JSONTEST_FIXTURE_LOCAL({FIX}, rule_core_settings) {{",
              "  Json::StreamWriterBuilder builder;",
              "  JSONTEST_ASSERT(builder.settings_.isMember(\"arrayInlineLimit\"));",
              "  JSONTEST_ASSERT(builder.settings_[\"arrayInlineLimit\"] == Json::Value(0));",
              "  JSONTEST_ASSERT(builder.validate(nullptr));",
              "  builder[\"arrayInlineLimit\"] = 3;",
              "  JSONTEST_ASSERT(builder.validate(nullptr));",
              "}", ""]
        if "strictvalue" in R:
            bad = ["true", "2.5", "-1", "\"3\"", "1.0"]
            ok = ["0", "3", "Json::UInt(7)"]
            for i, x in enumerate(bad, 1):
                L += [f"JSONTEST_FIXTURE_LOCAL({FIX}, rule_strictvalue_c{i}) {{",
                      "  Json::StreamWriterBuilder builder;",
                      f"  builder[\"arrayInlineLimit\"] = {x};",
                      "  JSONTEST_ASSERT_THROWS(delete builder.newStreamWriter());", "}", ""]
            for i, x in enumerate([] if True else ok, len(bad) + 1):
                L += [f"JSONTEST_FIXTURE_LOCAL({FIX}, rule_strictvalue_c{i}) {{",
                      "  Json::StreamWriterBuilder builder;",
                      f"  builder[\"arrayInlineLimit\"] = {x};",
                      "  bool threw = false;",
                      "  try {",
                      "    delete builder.newStreamWriter();",
                      "  } catch (...) {",
                      "    threw = true;",
                      "  }",
                      "  JSONTEST_ASSERT(!threw);", "}", ""]
        return [Edit("src/test_lib_json/main.cpp", "append", "\n".join(L), role="test")]
