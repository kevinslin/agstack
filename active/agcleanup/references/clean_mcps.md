# `clean_mcps`

Reap orphaned Codex computer-history MCP helper processes belonging to the
current user without interrupting helpers used by active tasks.

## Trigger

Lead with this command when the user invokes `$agcleanup clean_mcps` or explicitly asks to terminate accumulated Codex computer-history MCP helpers.

Invoking this subcommand authorizes terminating only matching helpers that are
positively identified as orphaned. Never interrupt a helper that could belong
to an active task. Preserve the helper when ownership or activity is uncertain.
Do not ask for confirmation to terminate verified orphans.

## Workflow

1. Run the bundled executable: `./scripts/clean_mcps.py`. If sandboxing denies `/bin/ps` enumeration or signaling, rerun this exact executable with the required sandbox escalation.
2. Use `./scripts/clean_mcps.py --dry-run` only when the user requests a preview. Dry-run mode must never signal a process.
3. Read the executable's JSON-line output and report:
   - matching helpers discovered,
   - verified orphaned helpers eligible for cleanup,
   - active or uncertain helpers protected,
   - `SIGTERM` and `SIGKILL` signals sent,
   - orphaned and protected helpers remaining,
   - any signal errors.
4. Treat zero eligible orphans as a successful no-op, including when protected
   helpers remain.
5. Treat cleanup as complete only when the final process scan reports zero
   remaining eligible orphans and the executable exits successfully. Protected
   active or uncertain helpers must remain untouched.

## Guardrails

- Match only processes owned by the current user whose actual executable basename is `SkyComputerUseClient` and whose complete command is exactly `$CODEX_HOME/computer-use/Codex Computer Use.app/Contents/SharedSupport/SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient computer-history mcp`. When `CODEX_HOME` is unset, its default is `~/.codex`.
- Target a matching helper only when its current parent PID is exactly `1`,
  proving that its original owning process exited. Preserve every helper with
  a living parent because it may belong to an active task.
- Revalidate the orphaned parent PID immediately before every signal. If
  ownership or activity cannot be determined, fail closed and do not signal.
- Verify the executable separately from its argument string. Do not parse the space-containing macOS executable path with `shlex.split`, and do not infer identity from a substring match.
- Never target the current process, its parent, Codex app-server or renderer
  processes, other users' processes, other MCP families, or DevBox proxy and
  tunnel processes.
- Send `SIGTERM` first. Send `SIGKILL` only to matching helpers that survived a prior `SIGTERM`; revalidate each PID immediately before every signal.
- Re-scan for respawned matching helpers in bounded sweeps and require a short quiet period before reporting zero remaining processes.
- Do not substitute broad `pkill`, `killall`, process-name-only matching, or parent-process termination for the bundled executable.

## Examples

`$agcleanup clean_mcps`

Terminate verified orphaned helpers while preserving every active or uncertain
computer-history MCP.

`$agcleanup clean_mcps --dry-run`

List matching helper PIDs without sending signals.
