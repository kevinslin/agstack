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
- specs/{{spec_number}}-{{spec_slug}}/artifacts: Durable supporting artifacts attached to this spec, including operator runbooks, handoff instructions, and other concrete deliverables.
- specs/{{spec_number}}-{{spec_slug}}/artifacts/{{artifact}}: One durable supporting artifact for this spec.
- specs/{{spec_number}}-{{spec_slug}}/flows: Flow docs for this spec. Use concise kebab-case flow names, following the specy flow-doc naming contract.
- specs/{{spec_number}}-{{spec_slug}}/flows/{{flow}}: Flow doc for a specific spec behavior or execution path.
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
