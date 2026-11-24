# Add `Json::Value::merge` (deep merge of JSON documents)

JsonCpp can build and edit `Json::Value` trees but offers no way to overlay one document on another (configuration defaults, patches, ...). Add the member function described below. If two requirements could both apply to the same pair of values, the one listed first takes precedence. Object member order is not significant (`Json::Value` keeps members sorted).

## Requirements

1. **Basic merge.** Add a public member function `Value& merge(const Value& patch, bool overwrite = true)` to `Json::Value` (declared in `include/json/value.h`, defined in `src/lib_json/json_value.cpp`). It merges `patch` into the receiver (`*this`), never modifies `patch`, copies (does not alias) whatever it takes from `patch`, and returns a reference to the receiver. If both the receiver and `patch` are objects, then for every member of `patch` the receiver ends up with a member of that name holding a copy of the patch's value (it is added when absent and replaced when present); receiver members that `patch` does not mention are untouched. If either of the two is not an object (null, bool, number, string or array), the receiver becomes a copy of `patch`. The `overwrite` argument only has an effect where a later requirement says so.
2. **Null deletes.** A member of the patch object whose value is null is never copied into the receiver: if the receiver has a member of that name, that member is removed, otherwise nothing happens. This concerns only the members of objects that are being merged member by member (the top-level objects, and nested objects when they are merged recursively). A patch value that is copied or assigned as a whole (for instance a nested object that replaces, or is added as, a receiver member) is copied verbatim, nulls inside it included. A null `patch` as a whole (not a member) is handled by the basic merge.
3. **Keep on kind mismatch.** Classify values into three kinds: object, array, and scalar (null, bool, any number, string). When the receiver and the patch both have a member of the same name and those two member values are of different kinds, the receiver's value is kept unchanged. Values of the same kind are handled by the other requirements. This applies to members only, never to the receiver and patch as a whole.
4. **Deep merge.** When the receiver and the patch both have a member of the same name and both member values are objects, those two objects are merged member by member, recursively, by the same rules, instead of the patch's object replacing the receiver's.
5. **Depth limit.** Recursive object merging stops at depth 2. Count depth as follows: members of the top-level objects are at depth 1, members of their members at depth 2, and so on. Two object-valued members at depth d are merged recursively only if d < 2; otherwise the patch's object replaces the receiver's (as in the basic merge).
6. **Self merge.** Merging a value into itself, `v.merge(v)`, leaves `v` unchanged (whatever its content).

## Notes

- Do not modify existing tests. Hidden tests cover every numbered requirement above and the repository's existing test-suite must keep passing.
- Anything not stated above is unspecified and is not tested.
