---
created: {{date}}
updated: {{date}}
last_updated_session: {{agent}}/{{session-id}}
---

# {{behavior}} Logic Trace

## Overview

{{One or two sentences describing the behavior and the trace boundary.}}

## Logic

```ts
{{entrypoint}}
    log "{{grepable start log}}"

    {{main execution path}}

    if not request.dry_run
        {{normal write or side effect}}

    log "{{grepable finish log}}"
```

## Exceptions

- {{Important early exit or stop condition, or `None identified`.}}

## State

- {{Persistent state fact needed to understand the flow, or `None identified`.}}

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog

- {{YYYY-MM-DD HH:MM}}: {{description of update}} ({{agent session id}} - {{git sha}})
