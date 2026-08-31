# integ-proof Schema

Source: `schema.yaml`

Inspect this schema with the installed `mem` command:

```bash
mem schema show integ-proof
mem schema describe integ-proof
```

```text
integ-proof [version=1.0 extension=md]
|-- variables
|   |-- proof: *, default=proof
|   `-- scenario: *
|-- tree
    `-- {{proof}}
        |-- proof
        |-- scenario
        |   `-- {{scenario}}
        |-- scripts
        `-- raw
```

## Descriptions

- {{proof}}: Integration behavior proof directory.
- {{proof}}/proof: Root behavior proof for one claim, target, status, and scenario result summary.
- {{proof}}/scenario: Live behavior scenarios with embedded config, observations, and raw artifact links.
- {{proof}}/scenario/{{scenario}}: One live behavior scenario with purpose, preconditions, action, expectation, observation, related raw artifacts, and notes.
- {{proof}}/scripts: Proof-local helper scripts for collecting, normalizing, summarizing, or validating proof artifacts.
- {{proof}}/raw: Arbitrary raw proof artifacts, logs, transcripts, command outputs, screenshots, JSON, and generated files.
