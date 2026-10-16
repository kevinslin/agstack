# Task attachments

These flows link a UTF-8 text file to a tracked task. The CLI updates an
existing file in place; the dashboard copies browser-selected content into
agtask-managed storage.

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

`$agtask <file.md>` composes child creation with this same attachment flow. It
first reads the Markdown task and relevant context through `$dendron`, creates
and verifies exactly one tracked child, then selects that child's real session
ID for `attach`. The invoking parent never receives the attachment. A queued
child without a real session ID is reported with attachment pending until its
session materializes and is registered.

Dashboard JSON derives each attachment's basename and `vscode://file` URL.
List and detail pages render those URLs as `file` badges without changing the
row-click behavior for the rest of the task row.

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant Server as tokenized loopback server
    participant Managed as managed attachment storage
    participant DB as SQLite ledger

    User->>Browser: press a on active or hovered task
    Browser->>User: native Markdown or text file picker
    User->>Browser: choose one file
    Browser->>Server: POST task attachment with basename and bytes
    Server->>Server: validate host, token, origin, media type, name, size, UTF-8
    Server->>DB: BEGIN IMMEDIATE; resolve task
    Server->>Managed: atomic 0600 copy with status + source
    Server->>DB: insert attachment, update timestamp, append event
    Server->>DB: commit
    Server-->>Browser: attachment projection
    Browser->>Server: refresh dashboard snapshot
    Browser-->>User: success notice and file badge
```

The upload route accepts `.md`, `.markdown`, and `.txt` basenames and at most
1 MiB. Its exact loopback host and origin checks supplement the opaque token
path. Managed paths are rooted beside the ledger beneath private `0700`
directories, with a distinct opaque directory per upload so a repeated name
cannot overwrite an earlier file. A failed ledger write rolls back the row and
removes the copied file. Invalid or failed uploads leave neither an attachment
row nor a managed file.
