---
name: close
description: Archive the exact Codex chat without task bookkeeping or Git cleanup.
---

# Close

Use for `trigger:close` or `trigger:close <thread-id>`.

1. Resolve the explicit real thread ID, or the authoritative current chat ID.
   Resolve its actual host. Do not select a chat from recency or title alone.
2. Discover the native `set_thread_archived` schema and archive that exact chat.
3. Report verified archive state or the exact error. Already archived is a no-op.

This shortcut does not update a ledger or Sites, run lifecycle hooks, finalize
Git work, delete worktrees, or remove pins. Never reopen or unarchive the target.
