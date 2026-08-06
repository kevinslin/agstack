# Beads Usage with Feature Specs

Use beads to track meaningful implementation work and dependencies across
sessions. A feature spec does not need named phases to use beads.

## Read project instructions first

If `skills/.config/dev.beads.instructions.md` exists at the project root, read it and
follow its rules. Use it for project-specific naming, shortcut rules, and sync policy.

## Map implementation work to beads

1. Create a top-level bead for the plan. Include the plan title and link to the plan
   doc in the bead description.
2. Create a bead for each independently tracked implementation step, or for each
   named phase when the plan genuinely requires phases.
3. Add dependencies only where implementation order requires them.

Example:

```bash
bd create "Plan: add cache layer" -p 2
bd create "Phase 1: research" -p 2 --deps "blocks:bd-123"
bd create "Phase 2: implementation" -p 2 --deps "blocks:bd-124"
bd create "Phase 3: testing and rollout" -p 2 --deps "blocks:bd-125"
```

## Use beads for each tracked unit

For every tracked implementation step or phase:

- Set the phase bead to in progress before starting:
  `bd update <id> --status in_progress`
- If new work is discovered, create a linked bead:
  `bd create "Follow-up: <title>" -p <priority> --deps "discovered-from:<id>"`
- Close the phase bead when complete:
  `bd close <id>`

At the end of a session, sync beads:

```bash
bd sync --from-main
```

## Default rules (if project file is missing)

- Use bd for all task tracking; do not use markdown TODOs.
- Use priorities 0-4 or P0-P4.
- Link discovered work with `discovered-from` dependencies.
- Run `bd sync --from-main` before ending a session.
