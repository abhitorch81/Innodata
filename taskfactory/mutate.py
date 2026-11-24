"""Language-aware (but light-weight) mutation operators for patch-level mutation testing.

Mutants are produced from the *text of the reference edits* (never from a diff), so every
mutant is "reference implementation with one small plausible bug" - the kind of mistake a
coding agent actually makes (off-by-one, flipped condition, wrong connective, ...).
"""
from __future__ import annotations
import copy
import random
import re

PY, CPP, TS = "python", "cpp", "ts"

_OPS = [  # (name, regex, replacement)
    ("seq->sne", r"(?<![=!<>])===(?!=)", "!=="),
    ("sne->seq", r"!==", "==="),
    ("eq->ne", r"(?<![=!<>])==(?!=)", "!="),
    ("ne->eq", r"!=(?!=)", "=="),
    ("===->!==", r"===", "!=="),
    ("!==->===", r"!==", "==="),
    ("le->lt", r"<=", "<"),
    ("ge->gt", r">=", ">"),
    ("lt->le", r"(?<![<-])<(?![<=])", "<="),
    ("gt->ge", r"(?<![>-])>(?![>=])", ">="),
    ("and->or", r"\band\b", "or"),
    ("or->and", r"\bor\b", "and"),
    ("&&->||", r"&&", "||"),
    ("||->&&", r"\|\|", "&&"),
    ("+->-", r" \+ ", " - "),
    ("-->+", r" - ", " + "),
    ("*->/", r" \* ", " / "),
    ("True->False", r"\bTrue\b", "False"),
    ("False->True", r"\bFalse\b", "True"),
    ("true->false", r"\btrue\b", "false"),
    ("false->true", r"\bfalse\b", "true"),
    ("int+1", r"(?<![\w.\"'])(\d+)(?![\w.\"'])", lambda m: str(int(m.group(1)) + 1)),
    ("drop-not", r"\bnot\s+", ""),
    ("drop-!", r"(?<![=!<>])!(?!=)", ""),
    ("first->last", r"\[0\]", "[-1]"),
]


def _is_comment(line: str, lang: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if lang == PY:
        return s.startswith(("#", "import ", "from "))
    return s.startswith(("//", "*", "/*", "#include", "import ", "export {"))


def line_mutants(line: str, lang: str):
    out = []
    code = line
    # protect string literals from mutation (very rough, good enough for operators above)
    for name, rx, rep in _OPS:
        for m in re.finditer(rx, code):
            pre = code[: m.start()]
            if pre.count('"') % 2 or pre.count("'") % 2 and lang == PY:
                continue
            new = code[: m.start()] + (rep(m) if callable(rep) else rep) + code[m.end():]
            if new != code:
                out.append((name, new))
    # condition negation
    s = line.strip()
    ind = line[: len(line) - len(line.lstrip())]
    if lang == PY:
        m = re.match(r"(\s*)(if|elif|while) (.+):\s*$", line)
        if m:
            out.append(("negate-cond", f"{m.group(1)}{m.group(2)} not ({m.group(3)}):"))
    else:
        m = re.match(r"(\s*)(if|while) \((.+)\) \{\s*$", line)
        if m:
            out.append(("negate-cond", f"{m.group(1)}{m.group(2)} (!({m.group(3)})) {{"))
    return out


def edit_mutants(edits, lang, seed=0, limit=40, roles=("impl",)):
    """Yield (label, edits') where edits' is a deep copy with one line of one edit mutated."""
    cands = []
    for ei, e in enumerate(edits):
        if e.role not in roles or not e.text:
            continue
        in_doc = False
        for li, line in enumerate(e.text.split("\n")):
            if lang == PY and line.count('"""') % 2 == 1:
                in_doc = not in_doc
                continue
            if in_doc or _is_comment(line, lang):
                continue
            for name, new in line_mutants(line, lang):
                cands.append((ei, li, name, line, new))
    random.Random(seed).shuffle(cands)
    # spread across distinct operators first so the sample isn't one repeated operator
    seen, picked = {}, []
    for c in sorted(cands, key=lambda c: 0):
        key = (c[0], c[2])
        if seen.get(key, 0) >= 2:
            continue
        seen[key] = seen.get(key, 0) + 1
        picked.append(c)
        if len(picked) >= limit:
            break
    for ei, li, name, old, new in picked:
        es = copy.deepcopy(edits)
        lines = es[ei].text.split("\n")
        lines[li] = new
        es[ei].text = "\n".join(lines)
        label = f"{es[ei].path}:{li + 1} {name}: `{old.strip()[:70]}` -> `{new.strip()[:70]}`"
        yield label, es
