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
    |-- specs
    |-- flows
    |   `-- {{flow}}
    |-- cook
    |   `-- {{cook}}
    `-- reports
        `-- {{report}}
```

## Descriptions

- specs: Project spec directory.
- flows: Project-level flow docs.
- flows/{{flow}}: Project-level flow doc for a behavior or execution path.
- cook: Project-level cookbooks and reusable recipes.
- cook/{{cook}}: Project-level cookbook or reusable recipe.
- reports: Project-level reports.
- reports/{{report}}: Project-level report.
