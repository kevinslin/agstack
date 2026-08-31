# code-core Schema

Source: `schema.yaml`

Inspect this schema with the installed `mem` command:

```bash
mem schema show code-core
mem schema describe code-core
```

```text
code-core [version=1.0 extension=md]
|-- tree
    |-- readme
    |-- assets
    |-- concepts
    |-- dev
    |   |-- qa
    |   `-- obs
    |-- flow
    |   `-- {{flow}}
    |-- arch
    |   `-- {{arch}}
    |-- pr
    |   `-- {{num}}-{{slug}}
    |-- api
    |   `-- {{api_name}}
    |-- t
    |   `-- {{name}}
    `-- ref
```

## Descriptions

- readme: general overview of code
- assets: non-markdown files
- concepts: index of various concepts
- dev: how to setup for development
- dev/qa: testing
- dev/obs: observability
- flow: execution-flow documentation
- flow/{{flow}}: flow doc for a specific execution path
- arch: architecture documentation for a named system, subsystem, workflow, or service boundary
- arch/{{arch}}: architecture doc for a specific system, subsystem, workflow, or service boundary
- pr: PR code-change flow docs. Use `pr/{{num}}-{{slug}}.md`, where `num` is the pull request number and `slug` is the lowercase hyphenated PR title; the document should describe the execution or behavior flow changed by the PR, not the pull request lifecycle.
- pr/{{num}}-{{slug}}: flow doc for the code changes in a specific pull request
- api: api reference
- api/{{api_name}}: api reference
- t: domain-specific topic namespace
- t/{{name}}: domain-specific topic note
- ref: self-contained functionality references
