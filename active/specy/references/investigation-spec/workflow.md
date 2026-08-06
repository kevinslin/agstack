# Investigation Spec Workflow

## Use When

- Diagnosing a bug with unclear or competing root-cause hypotheses
- Capturing a structured debugging plan before implementing a fix
- Handing off an investigation in progress without losing context
- Documenting evidence for lifecycle, ordering, or state-propagation failures

## Template

- `./references/investigation-spec/template.md`

## Constants

- %%OUTPUT_DIR: $DOCS_ROOT/specs/
- %%OUTPUT_FILE: %%OUTPUT_DIR{YYYY-MM-DD}-{topic}.md

## Instructions

1. Define the bug symptom, expected behavior, and current impact.
2. Choose a `{topic}` slug that stays within the `{YYYY-MM-DD}-{topic}.md` filename format and includes an `-investigation` qualifier when needed to avoid collisions.
3. Copy `./references/investigation-spec/template.md` to %%OUTPUT_FILE.
4. Build a hypothesis table with a fastest falsifier for each branch.
5. Build a state timeline for critical values from write to read.
6. Record evidence (logs, code locations, traces) per hypothesis outcome.
7. Include a `Context Propagation Contract` section that captures:
   - source of truth
   - initialization timing
   - transform rules
   - snapshot boundaries
   - expected consumers
8. Document root cause (or current best-supported hypothesis), fix strategy, and validation plan.
9. If the investigation is turning into implementation work, add an `Implementation Handoff` section or create a linked feature spec. Do not treat diagnostic vocabulary as the implementation contract by default.
10. When the fix changes data/API/CLI/config/migration output, the handoff
    feature spec must capture the existing owner and consumers, selected target
    behavior, and justification for new fields or execution paths in its
    `Contract` section. Add a decision table only when it clarifies genuinely
    state-dependent behavior.
11. Keep in-progress specs under `$DOCS_ROOT/specs/`. When the spec is complete, move it to `$DOCS_ROOT/specs/.archive/` without renaming it.
12. Resolve the current agent session id via `dev.llm-session` and include it in the `## Changelog` entry before handoff. Use a changelog timestamp with date, hour, and minute in `YYYY-MM-DD HH:MM` format.

## Authoring Requirements

- Use concrete evidence, not only speculation.
- Keep hypothesis branches mutually distinguishable and falsifiable.
- When root cause is still unknown, clearly mark current confidence and next highest-value probe.
