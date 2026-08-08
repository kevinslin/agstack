# `clean_devbox_connections`

Reap orphaned DevBox websocket proxy and tunnel pairs without interrupting active SSH-owned connections.

## Trigger

Lead with this command when the user invokes `$agcleanup clean_devbox_connections` or explicitly requests cleanup of orphaned DevBox websocket proxy connections.

Invoking the subcommand authorizes terminating matching orphaned proxy and tunnel pairs. Do not ask for confirmation.

## Workflow

1. Run `./scripts/clean_devbox_connections.py`. If macOS sandboxing blocks `/bin/ps` process enumeration or signaling, rerun this exact bundled executable with the required sandbox escalation.
2. Run `./scripts/clean_devbox_connections.py --dry-run` only when the user asks for a preview. Preview mode must never signal a process.
3. Parse the JSON-line output and report the initial and remaining orphaned proxy/tunnel counts, `SIGTERM`/`SIGKILL` counts, active proxy counts before and after cleanup, and any recorded errors.
4. Treat zero matching orphaned pairs as a successful no-op.
5. Claim completion only when the executable exits successfully, reports zero remaining targeted proxies, and reports the same active proxy count before and after cleanup.

## Guardrails

- Match only a process owned by the current user whose independently verified actual executable basename is `dbox-proxy`, whose full command contains `_websocket-proxy`, and whose parent PID is exactly `1`.
- Classify that orphaned proxy only when it has a direct child owned by the current user whose independently verified actual executable basename is `wstunnel`.
- Never target active SSH-owned proxy chains, non-orphaned proxies, another user's processes, shell wrappers, similarly named executables, or unrelated standalone tunnels. Executable identity must come from a separate `/bin/ps` `comm` snapshot; command-text substrings are not executable verification.
- Revalidate executable identity, process owner, complete command, process start time, and relevant parent relationship immediately before every signal. Reject reused PIDs and replacement proxies. A previously terminated tunnel may be reparented to PID `1` before bounded `SIGKILL` escalation.
- Send `SIGTERM` to matching tunnel children first, wait for them to exit, and escalate only surviving children that already received `SIGTERM`. Signal a verified orphaned parent only after its matching children are gone; apply the same bounded `SIGTERM`-then-`SIGKILL` behavior to the parent.
- Re-scan in bounded sweeps, preserve and verify the count of active current-user proxy chains, and report permission or signaling failures explicitly.
- Never substitute `pkill`, `killall`, process-name-only matching, broad SSH termination, or an unverified wrapper command for the bundled executable.

## Examples

`$agcleanup clean_devbox_connections`

Remove every verified orphaned DevBox proxy/tunnel pair while preserving active connections.

`$agcleanup clean_devbox_connections --dry-run`

List matching orphaned proxy/tunnel pairs and the active proxy count without sending signals.
