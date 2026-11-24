# Add option relations (`conflicts_with`, `requires`, exclusive groups) to `click.Option`

Command-line tools often need rules such as "`--json` and `--csv` cannot be combined". Click has no declarative support, so every application re-implements it in callbacks. Add it to `click.Option`. The hidden tests build commands with options named `alpha`..`hotel` and the exact kwargs described below.

## Requirements

1. **Conflicting options.** `click.Option` (and therefore `@click.option`) gains a keyword `conflicts_with`: a sequence of *parameter names* (the Python names, e.g. `"bravo"`, not flags). When the option and any option it names are both *provided*, parsing fails with `click.UsageError` (exit code 2) before the command callback runs. An option is *provided* when its value came from the command line (`ctx.get_parameter_source(name) is ParameterSource.COMMANDLINE`) - defaults, `default_map` and environment variables do not count. Names that match no option of the command, and an option's own name, are ignored. A pair that declares the conflict on both sides is reported once. The error message mentions, for every option involved in a reported violation, that option's first declared option string (for example `--alpha`), and no other option string. The check runs once per command in `Command.parse_args`, after all parameters were processed.
2. **Environment counts as provided.** Values that came from an environment variable (`ParameterSource.ENVIRONMENT`) also count as *provided* for every relation.
3. **Falsy values do not count.** An option whose converted value is falsy (`0`, an empty string, a boolean flag set to `False` as by `--no-echo`, an empty tuple) does not count as provided even if it appeared on the command line.
4. **Report every violation.** Violations are found by scanning the command's options in declaration order: for each provided option, first its `conflicts_with` names in listed order, then its `requires` names in listed order; group violations come after all per-option violations, ordered by the declaration position of the group's first provided member. The raised `UsageError` reports all violations, one per line (without this rule: only the first violation is reported).

## Notes

- Do not modify existing tests. Hidden tests cover every numbered requirement above and the repository's existing test-suite must keep passing.
- Anything not stated above is unspecified and is not tested.
