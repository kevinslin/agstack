# Concise Instruction Docs

Write an operator interface, not an implementation narrative. Document what a
person must supply, run, recognize, or recover from. Leave orchestration details
in the owning skill or implementation reference.

The governing principle: remove explanation, not information required for the
command to succeed safely.

## Style

1. Lead with the single intended action.
   - State what the command accomplishes.
   - Move directly to prerequisites.
2. Follow the operator's sequence.
   - `prerequisites -> inputs -> command -> completion -> recovery -> rollback`
3. Prefer short bullet fragments.
   - Use lowercase, noun-led fragments for requirements.
   - Reserve full sentences for decisions, warnings, and invariants.
4. Separate required inputs from optional inputs.
   - Put defaults and the reason to override them inline.
   - Example: `` `devbox_cluster`: defaults to `devbox-2`; override only when the target tenant requires another cluster ``.
5. Explain choices, not machinery.
   - Keep distinctions the operator must choose between.
   - Remove internal phases, subcommands, milestones, and state transitions owned elsewhere.
6. Prefer one realistic example over several paragraphs.
   - Show the expected invocation shape with plausible values.
7. Describe lifecycle concepts in operator terms.
   - Prefer "resume the same task" and "complete at `operational`" over internal state-machine names.
8. Keep exact terminal evidence.
   - Give an objective success output or stopping condition.
9. Retain terse safety boundaries.
   - State recovery invariants, rollback authorization, and destructive limits.
10. Link to canonical detail instead of duplicating it.
    - Let the instruction doc own human inputs and completion criteria.
    - Let the skill or implementation reference own execution mechanics.

## Template

````markdown
# <Verb> <object>

<One-sentence purpose>

## Prerequisites

- <required access or state>
- <where to run the command>

## 1. Collect inputs

Required:

- `<name>`: <meaning>

Optional:

- `<name>`: defaults to <value>; override when <reason>

## 2. Run

<One command and one realistic example>

## Completion

<Exact success output or condition>

## Troubleshooting

<One recovery invariant>

## Rollback

<Authorization boundary and canonical recovery entrypoint>

## Related

- <canonical implementation reference>
````

## Correctness Guardrails

Do not preserve brevity at the expense of correctness:

- verify that example values map to the fields they claim to populate
- quote YAML scalars that could parse as comments or null values
- use the exact identifier type required by the command, such as a channel ID rather than a display name
- include required file-permission steps, such as mode `0600`, when preflight enforces them
- keep required and optional labels consistent across prose, examples, and command arguments
- remove trailing whitespace and end the file with a newline

Before publishing, run the documented command when feasible and compare its
real completion evidence with the guide.
