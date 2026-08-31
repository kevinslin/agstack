# specs Schema

Source: `schema.yaml`

Inspect this schema with the installed `mem` command:

```bash
mem schema show specs
mem schema describe specs
```

```text
specs [version=1.0 extension=md]
|-- variables
|   |-- spec_number: *, default=1
|   |-- spec_slug: *, default=bootstrap
|   |-- artifact: *
|   |-- flow: *
|   |-- cook: *
|   |-- subspec: *, default=1.1
|   |-- subspec_slug: *
|   |-- report: *
|   |-- proof: *, default=proof
|   `-- scenario: *
|-- tree
    `-- specs
        |-- .archive
        `-- {{spec_number}}-{{spec_slug}}
            |-- spec
            |-- handoff
            |-- progress
            |-- learnings
            |-- artifacts
            |   `-- {{artifact}}
            |-- flows
            |   `-- {{flow}}
            |-- cook
            |   `-- {{cook}}
            |-- milestones
            |   `-- {{subspec}}-{{subspec_slug}}
            |-- proofs
            |   `-- {{proof}}
            |       |-- proof
            |       |-- scenario
            |       |   `-- {{scenario}}
            |       |-- scripts
            |       `-- raw
            `-- reports
                `-- {{report}}
```

## Descriptions

- specs: Active numbered specs plus a root archive for completed or superseded spec units.
- specs/.archive: Completed or superseded spec units, including terminal milestone subspecs, moved here without renaming.
- specs/{{spec_number}}-{{spec_slug}}: One active numbered spec directory.
- specs/{{spec_number}}-{{spec_slug}}/spec: Main spec for this numbered unit, including goals, requirements, plan, validation, and open questions.
- specs/{{spec_number}}-{{spec_slug}}/handoff: Current resumption context, completed work, next action, blockers, and relevant files for this spec.
- specs/{{spec_number}}-{{spec_slug}}/progress: Spec-local implementation status, completed work, active work, next steps, and blockers.
- specs/{{spec_number}}-{{spec_slug}}/learnings: Durable takeaways discovered while executing this numbered spec.
- specs/{{spec_number}}-{{spec_slug}}/artifacts: Durable supporting artifacts attached to this spec, including operator runbooks, handoff instructions, and other concrete deliverables.
- specs/{{spec_number}}-{{spec_slug}}/artifacts/{{artifact}}: One durable supporting artifact for this spec.
- specs/{{spec_number}}-{{spec_slug}}/flows: Spec-local flow docs for proposed behavior, exploration, snapshots, or behavior that has not been promoted to canonical project flow.
- specs/{{spec_number}}-{{spec_slug}}/flows/{{flow}}: Spec-local flow doc for a proposed, exploratory, snapshot, or unpromoted behavior path.
- specs/{{spec_number}}-{{spec_slug}}/cook: Cookbooks and reusable recipes for this spec.
- specs/{{spec_number}}-{{spec_slug}}/cook/{{cook}}: Cookbook or reusable recipe for a recurring spec task.
- specs/{{spec_number}}-{{spec_slug}}/milestones: Optional milestone subspecs, numbered as 1.N where N increments from 1.
- specs/{{spec_number}}-{{spec_slug}}/milestones/{{subspec}}-{{subspec_slug}}: Milestone subspec document.
- specs/{{spec_number}}-{{spec_slug}}/proofs: Integration behavior proofs for this spec.
- specs/{{spec_number}}-{{spec_slug}}/proofs/{{proof}}: Integration behavior proof directory.
- specs/{{spec_number}}-{{spec_slug}}/proofs/{{proof}}/proof: Root behavior proof for one claim, target, status, and scenario result summary.
- specs/{{spec_number}}-{{spec_slug}}/proofs/{{proof}}/scenario: Live behavior scenarios with embedded config, observations, and raw artifact links.
- specs/{{spec_number}}-{{spec_slug}}/proofs/{{proof}}/scenario/{{scenario}}: One live behavior scenario with purpose, preconditions, action, expectation, observation, related raw artifacts, and notes.
- specs/{{spec_number}}-{{spec_slug}}/proofs/{{proof}}/scripts: Proof-local helper scripts for collecting, normalizing, summarizing, or validating proof artifacts.
- specs/{{spec_number}}-{{spec_slug}}/proofs/{{proof}}/raw: Arbitrary raw proof artifacts, logs, transcripts, command outputs, screenshots, JSON, and generated files.
- specs/{{spec_number}}-{{spec_slug}}/reports: Optional custom reports relevant to this spec.
- specs/{{spec_number}}-{{spec_slug}}/reports/{{report}}: Custom report relevant to this spec.
