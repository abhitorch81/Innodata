# Validation summary

19/19 tasks pass all gates; mean mutation kill 93%.

| task | rules | F2P | P2P | S5 kill | gate |
|---|---|---|---|---|---|
| click/duration-01 | core, compound, bare, fraction, case, spaces | 57 | 2653 | 91% | VALID |
| click/duration-02 | core, compound, ordered, bare, bounds | 50 | 2653 | 92% | VALID |
| click/duration-03 | core, compound, ordered, bare, case, negative, spaces, bounds | 68 | 2653 | 100% | VALID |
| click/duration-04 | core, fraction, case, bounds | 47 | 2653 | 100% | VALID |
| click/relations-01 | core, requires, falsy, groups, resilient, help | 32 | 2653 | 92% | VALID |
| click/relations-02 | core, falsy, groups, all, resilient, help | 32 | 2653 | 100% | VALID |
| click/relations-03 | core, env, falsy, all | 30 | 2653 | 100% | VALID |
| click/relations-04 | core, requires, all, help | 24 | 2653 | 100% | VALID |
| jsoncpp/arrayinline-01 | core, emptyelem, nestedarr, totalcount, noroot, commentguard, strictvalue | 30 | 137 | 88% | VALID |
| jsoncpp/arrayinline-02 | core, nestedarr, totalcount, noroot, maxwidth | 20 | 136 | 88% | VALID |
| jsoncpp/arrayinline-03 | core, emptyelem, maxwidth, strictvalue | 19 | 138 | 81% | VALID |
| jsoncpp/arrayinline-04 | core, emptyelem, nestedarr, totalcount, maxwidth, commentguard, strictvalue | 29 | 139 | 81% | VALID |
| jsoncpp/merge-01 | core, noover, keepmismatch, deep, depthlimit, arrconcat, arrunion | 59 | 133 | 100% | VALID |
| jsoncpp/merge-02 | core, nulldel, keepmismatch, deep, depthlimit, selfmerge | 45 | 133 | 92% | VALID |
| jsoncpp/merge-03 | core, noover, nulldel, keepmismatch, arrconcat, selfmerge | 53 | 133 | 100% | VALID |
| jsoncpp/merge-04 | core, nulldel, keepmismatch, deep, arrconcat, arrunion, selfmerge | 58 | 133 | 87% | VALID |
| zod/unique-01 | core, key, nullish, perindex, firstonly, message | 34 | 2875 | 90% | VALID |
| zod/unique-02 | core, key, deep, nullish, perindex, firstonly, types | 35 | 2875 | 89% | VALID |
| zod/unique-03 | core, key, deep, nullish, perindex, message, types | 35 | 2875 | 91% | VALID |
