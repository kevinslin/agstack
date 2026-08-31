# tool Schema

Source: `schema.yaml`

Inspect this schema with the installed `mem` command:

```bash
mem schema show tool
mem schema describe tool
```

```text
tool [version=1.0 extension=md]
|-- variables
|   |-- prefix: pkg, vpkg
|   `-- name: *
|-- tree
    `-- {{prefix}}
        `-- {{name}}
            |-- concepts
            |-- cli
            |-- dev
            |   |-- qa
            |   `-- obs
            |-- t
            |   |-- {{topic}}
            |   `-- {{name}}
            |-- ref
            |   `-- {{reference}}
            |-- api
            |   |-- {{api}}
            |   `-- {{api_name}}
            |-- readme
            |-- assets
            |-- flow
            |   `-- {{flow}}
            |-- arch
            |   `-- {{arch}}
            `-- pr
                `-- {{num}}-{{slug}}
```

## Descriptions

- {{prefix}}/{{name}}: general description
- {{prefix}}/{{name}}/concepts: main concepts
- {{prefix}}/{{name}}/cli: command-line usage guidance
- {{prefix}}/{{name}}/dev: development setup, tests, and debugging
- {{prefix}}/{{name}}/dev/qa: how to test changes
- {{prefix}}/{{name}}/dev/obs: observability
- {{prefix}}/{{name}}/t: domain-specific topic namespace
- {{prefix}}/{{name}}/t/{{topic}}: domain-specific topic note
- {{prefix}}/{{name}}/t/{{name}}: domain-specific topic note
- {{prefix}}/{{name}}/ref: self-contained functionality references
- {{prefix}}/{{name}}/ref/{{reference}}: self-contained functionality reference
- {{prefix}}/{{name}}/api: public module API namespace
- {{prefix}}/{{name}}/api/{{api}}: public interfaces for a module
- {{prefix}}/{{name}}/api/{{api_name}}: api reference
- {{prefix}}/{{name}}/readme: general overview of code
- {{prefix}}/{{name}}/assets: non-markdown files
- {{prefix}}/{{name}}/flow: execution-flow documentation
- {{prefix}}/{{name}}/flow/{{flow}}: flow doc for a specific execution path
- {{prefix}}/{{name}}/arch: architecture documentation for a named system, subsystem, workflow, or service boundary
- {{prefix}}/{{name}}/arch/{{arch}}: architecture doc for a specific system, subsystem, workflow, or service boundary
- {{prefix}}/{{name}}/pr: PR code-change flow docs. Use `pr/{{num}}-{{slug}}.md`, where `num` is the pull request number and `slug` is the lowercase hyphenated PR title; the document should describe the execution or behavior flow changed by the PR, not the pull request lifecycle.
- {{prefix}}/{{name}}/pr/{{num}}-{{slug}}: flow doc for the code changes in a specific pull request
