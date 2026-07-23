# Task attachments

This flow links a local text file to the invoking tracked task.

```mermaid
sequenceDiagram
    participant User
    participant Skill as agtask skill
    participant CLI as agtask CLI
    participant File as local file
    participant DB as SQLite ledger

    User->>Skill: $agtask attach <file>
    Skill->>Skill: resolve invoking session ID
    Skill->>CLI: attach <file> --session-id <id>
    CLI->>DB: BEGIN IMMEDIATE; resolve task
    CLI->>File: read UTF-8 text and frontmatter
    CLI->>DB: insert unique attachment and event
    CLI->>File: atomic replacement with status + source
    CLI->>DB: commit
    CLI-->>Skill: thread, files, attachment result
    Skill-->>User: attached path and copied status
```

The ledger stores the resolved absolute path. The file receives the task's
current status and `codex://threads/<session_id>` source link. An exact retry
does not duplicate the relationship or event, but repairs those two managed
frontmatter fields. Attached files are not continuously synchronized when a
task later changes status.

Dashboard JSON derives each attachment's basename and `vscode://file` URL.
List and detail pages render those URLs as `file` badges without changing the
row-click behavior for the rest of the task row.
