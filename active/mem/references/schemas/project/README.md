# project Schema

Source: `schema.yaml`

Inspect this schema with the installed `mem` command:

```bash
mem schema show project
mem schema describe project
```

```text
project [version=1.0 extension=md]
|-- variables
|   |-- flow: *
|   |-- cook: *
|   `-- report: *
|-- tree
    |-- design
    |-- progress
    |-- learnings
    |-- steering
    |-- specs
    |-- flows
    |   `-- {{flow}}
    |-- cook
    |   `-- {{cook}}
    `-- reports
        `-- {{report}}
```

## Descriptions

- design: Current project design, ownership boundaries, decisions, constraints, and open questions.
- progress: Project-level status, recent agent changes, current blockers, and next actions.
- learnings: Evidence-backed project lessons, reusable patterns, invalidated assumptions, and follow-up checks.
- steering: Explicit user instructions, corrections, preferences, and source pointers that govern project work.
- specs: Numbered project specs are maintained by the separate specs schema; keep this marker for project-root navigation.
- flows: Canonical project-level flow docs for current behavior.
- flows/{{flow}}: Canonical project-level flow doc for a current behavior or execution path.
- cook: Project-level cookbooks and reusable recipes.
- cook/{{cook}}: Project-level cookbook or reusable recipe.
- reports: Project-level reports.
- reports/{{report}}: Project-level report.
