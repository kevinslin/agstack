# Cleanup reports

Keep routine user-facing summaries succinct. When every command has verified
success and exhaustive required coverage, say `Everything is successful.`
Otherwise show only the issues found: command, concrete problem, and any action
needed. Do not list successful commands alongside issues. A request for detail
overrides this concise default.

Retain the full run timestamp, discovered commands, per-command counts, exact
errors, and coverage evidence in a detailed report or run artifact. Link it when
useful; do not omit failures or partial coverage to shorten the summary.

For the detailed report:

Group cleanup command outcomes under `Unsuccessful runs` first, then
`Successful runs`. Apply this order to manual runs and consolidated scheduled
reports. List each command exactly once; write `None` for an empty group.

- **Unsuccessful runs:** failed, blocked, awaiting confirmation, partially
  completed, or not verifiably completed commands. Include incomplete coverage,
  unresolved targets, missing completion output, and failed postconditions here,
  even when some cleanup succeeded. State the precise status, counts, failure
  or uncertainty, and any required user action.
- **Successful runs:** commands with verified completion and no unresolved
  coverage or execution failures. Include verified no-ops. Preserving active or
  protected resources as required by the command is not itself a failure;
  unresolved cleanup candidates belong in the unsuccessful group.

Keep the run timestamp and overall status above the groups. Preserve each
subcommand's required counts, exact errors, and coverage warnings. For a sweep,
identify every discovered command through its entry in one of the two groups.
Report overall success only when the unsuccessful group is empty; otherwise
report partial completion or failure as appropriate. Do not rerun cleanup just
to reformat an earlier report.
