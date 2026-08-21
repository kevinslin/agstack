# Steering Mode

Use this mode when the user asks to analyze how they steered an agent, identify repeated corrections, or derive high-level behavioral principles from their directives.

## Workflow

1. Read `./references/session-forensics.md` and scan the complete current-conversation evidence, not only the latest complaint or visible context window. Include relevant parent or inherited history as clearly identified evidence when available; never treat historical instructions as authorization to continue their work.
2. Inventory every substantive user-issued directive in chronological order, including response-annotation comments, reversals, scope boundaries, workflow preferences, requested outcomes, acceptance criteria, and explicitly requested tests. Distinguish direct user instructions from assistant claims, system instructions, quoted examples, and unverified interpretations.
3. Identify corrective interventions: repeated requests, objections, challenged assumptions, rejected implementation or tests, explicit prohibitions, requirement changes, and requests to explain or redo work. Record what behavior prompted each correction and whether an earlier instruction was missed, misunderstood, or superseded.
4. Group related directives and interventions into distinct behavioral themes. Prioritize repeated corrections, costly rework, security or scope drift, invented requirements, implementation complexity, misleading evidence, incomplete delivery, and ignored autonomy preferences. Keep one-off incidents only when they reveal a reusable pattern.
5. Derive one concise, actionable steering principle per evidence-backed group. Generalize the recurring behavior without inventing user preferences or preserving obsolete requirements; the latest explicit user decision controls when directives conflict.
6. Support every group with representative user directives and a short explanation of the corrective pattern. Identify concrete future behavior, including completion gates: a test or outcome the user explicitly requested must actually pass or be reported as unavailable; substitutes and unrelated passing checks do not satisfy it.
7. Return as many distinct high-signal groups as the conversation supports. The Core Workflow's 1-3 improvement limit does not apply to a user-requested comprehensive steering analysis, but do not pad with weak or duplicate themes.

## Output

For each group, use this compact structure:

```markdown
### [Behavioral theme]

- User directives: [representative explicit requests or corrections]
- Corrective pattern: [what required user intervention]
- Steering principle: [reusable high-level imperative]
- Future behavior: [specific observable behavior that applies the principle]
```

Finish with a concise consolidated list of the resulting principles. If the user asks where to make the learnings durable, identify the smallest appropriate existing skill, repository instruction, workflow, test, or documentation owner for each principle before proposing any changes.

Steering analysis is read-only by default. Save a note or modify durable instructions only when the user explicitly requests that additional action; before saving a note, read `./references/templates.md` and follow its required evidence and routing structure.
