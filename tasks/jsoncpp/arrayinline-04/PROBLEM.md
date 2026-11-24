# Add the `arrayInlineLimit` StreamWriterBuilder setting

In pretty mode `StreamWriterBuilder` writes every array one element per line, which makes lists of small numbers very tall. Add an opt-in setting that prints short arrays on one line. Examples use indentation of two spaces. The implementation belongs in `src/lib_json/json_writer.cpp` (document the setting in `include/json/writer.h`).

## Requirements

1. **The `arrayInlineLimit` setting.** Add a `StreamWriterBuilder` setting `"arrayInlineLimit"` (an unsigned integer). `setDefaults` must set it to `0` (so `settings_["arrayInlineLimit"]` is `0` on a fresh builder) and `validate()` must accept the key as a known setting. With value `0`, or when `"indentation"` is the empty string, the output is byte-for-byte what the writer produced before this change. Otherwise, with limit N > 0, a non-empty array that has at most N elements, every element being a simple value (null, bool, number or string), is written on a single line as `[ 1, 2 ]` (a space after `[` and before `]`), elements separated by `, ` and each formatted exactly as it would be otherwise. This holds for both `commentStyle` values. A single-line array follows its member name and colon directly (`"key" : [1, 2]`), appears on its own indented line when it is an element of a multi-line array, and starts the output when it is the root. Every array that is not written on a single line by these requirements is written exactly as before. When `commentStyle` is `"None"`, only arrays that qualify for a single line are tested.
2. **Empty containers count as simple.** An empty array (`[]`) or empty object (`{}`) element also counts as a simple value for the purpose of the single-line condition, and is written `[]` / `{}` inside the line. Non-empty objects never count.
3. **Nested single-line arrays.** A non-empty array element counts as a simple value if that array itself qualifies for a single line under these requirements (including the element-count limit); it is then written inline inside the outer line, in the same form. Arrays that do not qualify disqualify their parent.
4. **Limit counts leaves.** The limit N bounds the total number of simple values (empty containers included, when they count) found in the array at any depth, instead of only its direct elements. Every array, nested ones included, is judged by the leaves it contains.
5. **Width cap.** An array is written on a single line only if its single-line text, from `[` through `]`, is at most 28 characters long (strings count as written, quotes included). Otherwise it is written as before.
6. **Comments keep arrays expanded.** When `commentStyle` is `"All"`, an array with an element that has a comment attached to it (placement does not matter) is not written on a single line, so that the comment is preserved; it is written as before. A comment on the array itself does not matter. With `commentStyle` `"None"` comments are not written and have no effect.
7. **Strict setting validation.** `newStreamWriter()` throws a `std::exception` unless `"arrayInlineLimit"` is an integer value (`Json::intValue` or `Json::uintValue`) that is not negative. Reals (even whole ones), bools and strings are rejected. A setting that is missing behaves as `0`.

## Notes

- Do not modify existing tests. Hidden tests cover every numbered requirement above and the repository's existing test-suite must keep passing.
- Anything not stated above is unspecified and is not tested.
