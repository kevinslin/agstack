# `pkg` schema

Use this schema for package-scoped knowledge below an aggregate base. Its first schema node is `{{package}}`; the base's schema entry selects where that hierarchy is mounted.

```yaml
schemas:
  - name: pkg
    root: packages # packages/{{package}}/...
```

Use `root: .` for inline `{{package}}/...` or a nested root such as `projects/packages`. Omitting `root` preserves the historical `pkg/{{package}}/...` layout.

```text
<schema-root>/ # omitted for root: .; defaults to pkg
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
