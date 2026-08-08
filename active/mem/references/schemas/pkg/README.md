# `pkg` schema

Use this schema for package-scoped knowledge below an aggregate base.

```text
pkg/
  {{package}}/
    cook/       # global-core
    ref/        # global-core
    t/          # global-core
    readme      # code-core
    dev/        # code-core
    flow/       # code-core
    arch/       # code-core
    pr/         # code-core
    api/        # code-core
    specs/      # specs
```

`global-core` is mounted first and owns the overlapping `ref` and `t`
namespaces. `code-core` supplies the remaining code-documentation nodes, and
`specs` supplies package-local specification units. Parent values are passed to
each child schema only through explicit `vars` mappings.
