# `clean_mcps`

Reap accumulated Codex computer-history MCP helper processes belonging to the current user.

## Trigger

Lead with this command when the user invokes `$agcleanup clean_mcps` or explicitly asks to terminate accumulated Codex computer-history MCP helpers.

Invoking this subcommand authorizes terminating every matching helper, including
helpers that are active or currently serving an MCP request. Interrupting those
matching MCPs is explicitly permitted; activity is not a blocker, exclusion, or
reason to skip cleanup. Do not ask for confirmation.

## Workflow

1. Run the bundled executable: `./scripts/clean_mcps.py`. If sandboxing denies `/bin/ps` enumeration or signaling, rerun this exact executable with the required sandbox escalation.
2. Use `./scripts/clean_mcps.py --dry-run` only when the user requests a preview. Dry-run mode must never signal a process.
3. Read the executable's JSON-line output and report:
   - matching helpers discovered,
   - `SIGTERM` and `SIGKILL` signals sent,
   - matching helpers remaining,
   - any signal errors.
4. Treat zero initial matches as a successful no-op.
5. Treat cleanup as complete only when the final process scan reports zero remaining matches and the executable exits successfully. Otherwise report the exact remaining count and failures; do not claim success.

## Guardrails

- Match only processes owned by the current user whose actual executable basename is `SkyComputerUseClient` and whose complete command is exactly `$CODEX_HOME/computer-use/Codex Computer Use.app/Contents/SharedSupport/SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient computer-history mcp`. When `CODEX_HOME` is unset, its default is `~/.codex`.
- Terminate every matching helper even when it is active; a temporary
  interruption or reconnect of that computer-history MCP is expected and
  authorized.
- Verify the executable separately from its argument string. Do not parse the space-containing macOS executable path with `shlex.split`, and do not infer identity from a substring match.
- Never target the current process, its parent, Codex app-server or renderer
  processes, other users' processes, other MCP families, or DevBox proxy and
  tunnel processes.
- Send `SIGTERM` first. Send `SIGKILL` only to matching helpers that survived a prior `SIGTERM`; revalidate each PID immediately before every signal.
- Re-scan for respawned matching helpers in bounded sweeps and require a short quiet period before reporting zero remaining processes.
- Do not substitute broad `pkill`, `killall`, process-name-only matching, or parent-process termination for the bundled executable.

## Examples

`$agcleanup clean_mcps`

Terminate all current-user computer-history MCP helpers and verify that none remain.

`$agcleanup clean_mcps --dry-run`

List matching helper PIDs without sending signals.
