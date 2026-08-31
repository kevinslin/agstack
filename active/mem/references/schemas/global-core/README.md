# global-core Schema

Source: `schema.yaml`

Inspect this schema with the installed `mem` command:

```bash
mem schema show global-core
mem schema describe global-core
```

```text
global-core [version=1.0 extension=md]
|-- variables
|   |-- cook: *, default=guide
|   |-- reference: *, default=reference
|   `-- topic: *, default=topic
|-- tree
    |-- cook
    |   `-- {{cook}}
    |-- ref
    |   `-- {{reference}}
    `-- t
        `-- {{topic}}
```

## Descriptions

- cook: Task-oriented guides for completing workflows.
- cook/{{cook}}: Guide for completing a specific workflow.
- ref: References for facts that might not fit within a topic or might fit across multiple topics.
- ref/{{reference}}: Reference for a fact that might not fit within a topic or might fit across multiple topics.
- t: Topics for domain entities in the domain entity model for a given subject.
- t/{{topic}}: Topic for a domain entity in the domain entity model for a given subject.
