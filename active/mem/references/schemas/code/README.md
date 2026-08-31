# code Schema

Source: `schema.yaml`

Inspect this schema with the installed `mem` command:

```bash
mem schema show code
mem schema describe code
```

```text
code [version=1.0 extension=md]
|-- variables
|   |-- module: *, default=module
|   |-- date: *, default=YYYY-MM-DD
|   |-- system: *, default=system
|   |-- research_topic: *, default=topic
|   |-- service_design_topic: *, default=topic
|   |-- spec_num: *, default=01
|   |-- spec_topic: *, default=topic
|   |-- design_topic: *, default=topic-design
|   |-- investigation_topic: *, default=topic-investigation
|   |-- validation_topic: *, default=topic-validation
|   |-- archived_spec_num: *, default=00
|   |-- archived_spec_topic: *, default=archived-topic
|   |-- flow_topic: *, default=topic
|   |-- flow_ref: *, default=reference
|   |-- state_name: *, default=target-state
|   |-- recipe_name: *, default=change-recipe
|   |-- faq_topic: *, default=topic
|   |-- library: *, default=library
|   |-- vendor_reference: *, default=api
|   |-- vendor_topic: *, default=topic
|   `-- db_name: *, default=database
|-- tree
    `-- packages
        `-- {{module}}
            |-- navfile
            |-- dev
            |   |-- qa
            |   `-- obs
            |-- ref
            |-- ARCHITECTURE
            |-- architecture
            |   `-- {{date}}-architecture-{{system}}
            |-- research
            |   `-- {{date}}-research-{{research_topic}}
            |-- design
            |   `-- {{date}}-design-{{service_design_topic}}
            |-- specs
            |   |-- {{spec_num}}-{{spec_topic}}
            |   |-- {{date}}-{{design_topic}}
            |   |-- {{date}}-{{investigation_topic}}
            |   |-- {{date}}-{{validation_topic}}
            |   `-- .archive
            |       `-- {{archived_spec_num}}-{{archived_spec_topic}}
            |-- flows
            |   |-- core.init
            |   |-- core.exit
            |   |-- topic.{{flow_topic}}
            |   `-- ref.{{flow_ref}}
            |-- state
            |   `-- {{state_name}}
            |-- recipes
            |   `-- {{recipe_name}}
            |-- faq
            |   `-- {{date}}-{{faq_topic}}
            |-- vendor
            |   `-- {{library}}
            |       |-- README
            |       |-- reference
            |       |   `-- {{vendor_reference}}
            |       `-- topics
            |           `-- {{vendor_topic}}
            |-- db
            |   `-- {{db_name}}
            |-- readme
            |-- assets
            |-- concepts
            |-- flow
            |   `-- {{flow}}
            |-- arch
            |   `-- {{arch}}
            |-- pr
            |   `-- {{num}}-{{slug}}
            |-- api
            |   `-- {{api_name}}
            `-- t
                `-- {{name}}
```

## Descriptions

- packages: Package-level code documentation root.
- packages/{{module}}: Root module, service, package, or docs area containing code documentation.
- packages/{{module}}/navfile: Navigation map for the module, including purpose, aliases, key file paths, entrypoints, rg anchors, and related module navfiles.
- packages/{{module}}/dev: development setup, tests, and debugging
- packages/{{module}}/dev/qa: how to test changes
- packages/{{module}}/dev/obs: observability
- packages/{{module}}/ref: Catchall reference notes for module information that does not fit another code documentation area.
- packages/{{module}}/ARCHITECTURE: Project-wide architecture doc for the whole system, matching the specy architecture workflow default.
- packages/{{module}}/architecture: Dated architecture docs for subsystem or service-level architecture.
- packages/{{module}}/architecture/{{date}}-architecture-{{system}}: System or subsystem architecture doc.
- packages/{{module}}/research: Research briefs comparing technologies, approaches, or implementation options.
- packages/{{module}}/research/{{date}}-research-{{research_topic}}: Dated research brief for a specific topic.
- packages/{{module}}/design: Service design docs for staff-level service or system proposals.
- packages/{{module}}/design/{{date}}-design-{{service_design_topic}}: Service design doc.
- packages/{{module}}/specs: Active feature specs, feature designs, investigation specs, and validation specs.
- packages/{{module}}/specs/{{spec_num}}-{{spec_topic}}: Active feature spec with a monotonic two-digit prefix.
- packages/{{module}}/specs/{{date}}-{{design_topic}}: Optional dated feature design spec.
- packages/{{module}}/specs/{{date}}-{{investigation_topic}}: Optional dated investigation spec.
- packages/{{module}}/specs/{{date}}-{{validation_topic}}: Optional dated validation spec.
- packages/{{module}}/specs/.archive: Completed specs moved here without renaming.
- packages/{{module}}/specs/.archive/{{archived_spec_num}}-{{archived_spec_topic}}: Archived completed spec.
- packages/{{module}}/flows: Execution-flow documentation for lifecycle, topic, and reference flows.
- packages/{{module}}/flows/core.init: Core initialization flow.
- packages/{{module}}/flows/core.exit: Core cleanup or shutdown flow.
- packages/{{module}}/flows/topic.{{flow_topic}}: Optional topic flow for major functionality in a domain.
- packages/{{module}}/flows/ref.{{flow_ref}}: Optional reference flow for supporting behavior outside core/topic.
- packages/{{module}}/state: Terminal-output and state-derivation docs.
- packages/{{module}}/state/{{state_name}}: State doc for a target symbol or output surface.
- packages/{{module}}/recipes: Reproducible change recipes derived from a conversation or PR.
- packages/{{module}}/recipes/{{recipe_name}}: Step-by-step change recipe.
- packages/{{module}}/faq: Standalone FAQ docs; FAQ specs update target research docs in place and do not create files here.
- packages/{{module}}/faq/{{date}}-{{faq_topic}}: Standalone FAQ doc.
- packages/{{module}}/vendor: Project-focused third-party library documentation.
- packages/{{module}}/vendor/{{library}}: Vendor documentation root for one library.
- packages/{{module}}/vendor/{{library}}/README: Vendor overview doc.
- packages/{{module}}/vendor/{{library}}/reference: Optional API reference docs for vendor APIs used by the project.
- packages/{{module}}/vendor/{{library}}/reference/{{vendor_reference}}: Vendor API reference doc.
- packages/{{module}}/vendor/{{library}}/topics: Optional vendor topic deep-dives.
- packages/{{module}}/vendor/{{library}}/topics/{{vendor_topic}}: Vendor topic doc.
- packages/{{module}}/db: Database and persistence-layer documentation.
- packages/{{module}}/db/{{db_name}}: Database schema, model, migration, query, or storage behavior documentation.
- packages/{{module}}/readme: general overview of code
- packages/{{module}}/assets: non-markdown files
- packages/{{module}}/concepts: index of various concepts
- packages/{{module}}/flow: execution-flow documentation
- packages/{{module}}/flow/{{flow}}: flow doc for a specific execution path
- packages/{{module}}/arch: architecture documentation for a named system, subsystem, workflow, or service boundary
- packages/{{module}}/arch/{{arch}}: architecture doc for a specific system, subsystem, workflow, or service boundary
- packages/{{module}}/pr: PR code-change flow docs. Use `pr/{{num}}-{{slug}}.md`, where `num` is the pull request number and `slug` is the lowercase hyphenated PR title; the document should describe the execution or behavior flow changed by the PR, not the pull request lifecycle.
- packages/{{module}}/pr/{{num}}-{{slug}}: flow doc for the code changes in a specific pull request
- packages/{{module}}/api: api reference
- packages/{{module}}/api/{{api_name}}: api reference
- packages/{{module}}/t: domain-specific topic namespace
- packages/{{module}}/t/{{name}}: domain-specific topic note
