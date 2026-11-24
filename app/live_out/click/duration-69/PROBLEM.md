# Add a `Duration` parameter type

Click can parse integers, floats, dates and paths from the command line, but not durations such as `90s` or `1h30m`. Implement the type described below, following the conventions of the existing parameter types in `click/types.py`.

## Requirements

1. **Basic type.** Add a new parameter type `click.Duration` (defined in `click/types.py`, exported from the top-level `click` package) that converts a command-line string into a `datetime.timedelta`. Its `name` is `"duration"`. A valid value is a non-negative integer written with ASCII digits `0-9`, immediately followed by a unit suffix, with no whitespace anywhere. Supported units (lowercase only): `w` (weeks, 604800 s), `d` (days, 86400 s), `h` (hours, 3600 s), `m` (minutes, 60 s), `s` (seconds, 1 s), `ms` (milliseconds, 0.001 s). The result is the number multiplied by the unit's length. A `timedelta` passed to `convert` is returned unchanged. Any other input - including the empty string, unknown units, non-ASCII digits, and values too large for `timedelta` to represent - must fail by calling `self.fail(...)` (so users get the standard `BadParameter`, exit code 2) with a message that contains `repr()` of the offending input.

## Notes

- Do not modify existing tests. Hidden tests cover every numbered requirement above and the repository's existing test-suite must keep passing.
- Anything not stated above is unspecified and is not tested.
