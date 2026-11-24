# Add `.unique()` to `ZodArray`

Zod can bound the length of arrays but cannot say "no duplicates". Add a `unique` check to arrays following the style of the existing array methods. The hidden tests are vitest tests including type-level (`@ts-expect-error`) assertions.

## Requirements

1. **Basic uniqueness.** Add a method `unique(options?)` to `ZodArray` (classic API, `packages/zod/src/v4/classic/schemas.ts`) that adds a check and returns the same schema type (`this`). The check fails when two items of the array are equal under SameValueZero (the `Set` rule: `NaN` equals `NaN`, `0` equals `-0`, `"1"` does not equal `1`, `null` does not equal `undefined`, two distinct objects are never equal even if they look alike, the same object twice is). Items are compared as the *parsed output* values (so with `z.string().trim()` the items `" a"` and `"a"` are duplicates). Every issue it reports has `code: "custom"` and a non-empty `message`. An array without duplicates passes; the empty array and one-element arrays pass.
2. **Uniqueness by key.** `options.by` is an optional function `(item, index) => unknown`; when given, the keys it returns (instead of the items) are compared for equality.
3. **Ignore nullish.** `options.ignoreNullish: true`: items (or keys, when `by` is used) that are `null` or `undefined` never count as duplicates of each other.
4. **One issue per duplicate.** Instead of one issue for the whole array, report one issue for every duplicate occurrence, i.e. every item that equals some EARLIER item (the first occurrence is never reported). Each issue's `path` is `[index]` of that item, relative to the array (so inside `z.object({ tags })` the full path is `["tags", index]`), and issues are ordered by index. Without this behaviour there is exactly one issue and its `path` is the array's own (empty at top level).
5. **First duplicate only.** Only the issue for the first duplicate occurrence (lowest index) is reported.
6. **Custom message.** `options.message` (a string) is used as the `message` of every issue the check reports.

## Notes

- Do not modify existing tests. Hidden tests cover every numbered requirement above and the repository's existing test-suite must keep passing.
- Anything not stated above is unspecified and is not tested.
