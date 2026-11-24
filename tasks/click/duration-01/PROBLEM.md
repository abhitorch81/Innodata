# Add a `Duration` parameter type

Click can parse integers, floats, dates and paths from the command line, but not durations such as `90s` or `1h30m`. Implement the type described below, following the conventions of the existing parameter types in `click/types.py`.

## Requirements

1. **Basic type.** Add a new parameter type `click.Duration` (defined in `click/types.py`, exported from the top-level `click` package) that converts a command-line string into a `datetime.timedelta`. Its `name` is `"duration"`. A valid value is a non-negative integer written with ASCII digits `0-9`, immediately followed by a unit suffix, with no whitespace anywhere. Supported units (lowercase only): `w` (weeks, 604800 s), `d` (days, 86400 s), `h` (hours, 3600 s), `m` (minutes, 60 s), `s` (seconds, 1 s). The result is the number multiplied by the unit's length. A `timedelta` passed to `convert` is returned unchanged. Any other input - including the empty string, unknown units, non-ASCII digits, and values too large for `timedelta` to represent - must fail by calling `self.fail(...)` (so users get the standard `BadParameter`, exit code 2) with a message that contains `repr()` of the offending input.
2. **Compound values.** A value may consist of two or more number+unit segments written back to back, e.g. `1h30m`; its value is the sum of the segments. Every segment must carry its own unit and obeys all other rules (a segment like `30` without a unit makes the whole value invalid).
3. **Bare numbers.** A bare number with no unit (e.g. `90`) is accepted and means that many seconds. This is accepted only when the bare number is the entire input, never as a segment of a compound value.
4. **Fractional numbers.** The number in a segment (and a bare number) may have a fractional part: ASCII digits, a `.`, then ASCII digits (so `1.5h` and `0.25m` are valid, `.5s` and `5.s` are not). Arithmetic must be exact decimal arithmetic (not binary floating point), with the final total rounded half-even to the nearest microsecond.
5. **Case-insensitive units.** Unit suffixes are matched case-insensitively: `5M`, `1H30m`, `2MS` are valid (when the lowercase unit is supported). The suffix is matched as a whole.
6. **Whitespace tolerance.** Spaces and tab characters are tolerated: leading/trailing whitespace is ignored, and whitespace is allowed between a number and its unit (`5 m`) and between segments (`1h 30m`). Whitespace inside a number is still invalid, and an input of only whitespace is invalid.

## Notes

- Do not modify existing tests. Hidden tests cover every numbered requirement above and the repository's existing test-suite must keep passing.
- Anything not stated above is unspecified and is not tested.
