---
name: gen-notifier
description: "Top-level agents only: send exactly one final-state desktop notification before the final report."
dependencies: []
version: 1.2.1
---

# Task Completion Notifier

This skill sends desktop notifications using terminal-notifier to alert the user when a job has reached its final terminal state.

## When to Use This Skill

Use this skill in the following scenarios:

1. **User explicitly requests notification** - When the user says "notify me when done", "let me know when this finishes", etc.
2. **Long-running tasks** - Jobs that take significant time (builds, deployments, large refactors, test suites)
3. **Background tasks** - When the user might context-switch while waiting
4. **Default behavior** - By default, assume all jobs assigned to the top-level agent will require one notification unless the user specifies otherwise

## Core Rule

Use this skill only once per job, at the very end, after the work is finalized and immediately before you generate the final user-facing report.

- Use this skill only from the top-level or parent agent
- Do not use this skill from subagents, delegated workers, review workers, or background worker agents
- If you are a subagent or worker, report your terminal state to the parent agent instead; the parent agent owns the single final notification for the overall job
- Do not notify during intermediate steps
- Do not notify when you are still investigating or iterating
- Do not notify before verification, cleanup, or finalization is complete
- If the user explicitly asks for different timing, follow the user's instruction instead

## Memory Summary Suppression

Do not send a desktop notification for chronicle-related threads unless the user explicitly asks to override this suppression for that thread.

Treat a thread as chronicle-related when the primary work is about chronicle memory/resources, chronicle rollout summaries, or communication-triage workflows sourced from chronicle data.

Also suppress notifications when the primary work is a Skysight memory summary, including summaries synthesized from Skysight observations or injected Skysight memory context.

This suppression overrides the default "notify for all jobs" behavior, including long-running tasks.

## How to Notify

When a job reaches a finalized terminal state (`completed`, `needs_input`, or `errors`), send a notification using:

```bash
terminal-notifier -title "{DESCRIPTION OF JOB}" -message "{STATUS_OF_JOB} — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
```

The `-sound default` parameter makes a beeping sound to alert the user audibly.

### Click-to-open task

When the thread ID for the Codex task receiving the final report is available, make the entire notification clickable with `-open "codex://threads/{THREAD_ID}"`.

- Use the top-level recipient task's thread ID, never a delegated worker's thread ID
- Accept only a canonical UUID matching `^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$`
- If the thread ID is unavailable or invalid, omit `-open` and keep the original status-only message
- Do not use `-execute`; it invokes a shell when clicked and creates avoidable injection risk
- Do not add `-sender` or `-activate`; they change app identity or only bring an app forward instead of opening the task
- Treat the whole notification as the click target; terminal-notifier cannot render an inline hyperlink

### Status Values

Use one of these status values in the message:

- **completed** - Task finished successfully
- **needs_input** - Task requires user input to proceed
- **errors** - Task encountered errors and cannot proceed

### Title Format

The title should be a concise description of the job (3-8 words):

**Good examples:**
- "Build and Test Suite"
- "API Integration Implementation"
- "Database Migration"
- "Code Refactoring Complete"

**Bad examples:**
- "Task" (too vague)
- "The implementation of the new authentication system with JWT tokens and refresh token rotation" (too long)

## Notification Examples

### Successful Completion
```bash
terminal-notifier -title "API Integration Implementation" -message "completed — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
```

### Needs User Input
```bash
terminal-notifier -title "Database Migration Setup" -message "needs_input — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
```

### Encountered Errors
```bash
terminal-notifier -title "Build and Test Suite" -message "errors — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
```

## Notification Timing

Send the notification only when both conditions are true:

1. **The job is finalized** - Implementation, verification, cleanup, and any final checks are done, or you have reached a definitive blocked/error state
2. **You are about to report out** - The next step is the final user-facing response

Order of operations:

1. Finish the work
2. Verify and finalize the outcome
3. Send exactly one notification
4. Generate the final report to the user

## When NOT to Send Notifications

Don't send notifications for:

- Quick tasks (< 30 seconds)
- Intermediate steps of a larger task
- Minor clarifying questions
- Every tool execution
- Tasks where user is actively watching
- Cases where the job is not yet finalized
- Subagent, delegated-worker, review-worker, or background-worker completion
- Chronicle-related threads or Skysight memory-summary work, unless the user explicitly requests an override

## Best Practices

1. **One notification per task** - Don't spam multiple notifications
2. **Wait until final handoff** - Only notify when the job is fully finalized and you are about to produce the final report
3. **Be specific in title** - User should understand what completed
4. **Use appropriate status** - Accurately reflect the outcome
5. **Default timing can be overridden** - If the user explicitly asks for a different moment, follow that instead

## Example Workflows

### Successful Completion

User: "Implement the new authentication feature and notify me when done"

Assistant steps:
1. Implements authentication feature
2. Adds tests
3. Runs tests (all pass)
4. Finalizes the result and prepares the handoff
5. Sends notification with a verified thread ID: terminal-notifier -title "Authentication Feature" -message "completed — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
6. Generates the final user-facing report

### Needs User Input

User: "Set up the database migration"

Assistant steps:
1. Creates migration files
2. Discovers multiple valid approaches for schema design
3. Determines it cannot proceed without a user decision
4. Finalizes the blocked state and prepares the handoff
5. Sends notification with a verified thread ID: terminal-notifier -title "Database Migration Setup" -message "needs_input — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
6. Generates the final user-facing report

### Encountered Errors

User: "Run the full test suite and notify me"

Assistant steps:
1. Runs test suite
2. Encounters 5 failing tests
3. Attempts to fix but determines the task cannot be completed within scope
4. Finalizes the error state and prepares the handoff
5. Sends notification with a verified thread ID: terminal-notifier -title "Test Suite Execution" -message "errors — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
6. Generates the final user-facing report

## Implementation Notes

### Timing

Always send the notification after the job is finalized and immediately before the final user-facing report:

```
Assistant: I've completed implementing the authentication feature...

[Details of what was done]

[Runs terminal-notifier command]

[Final report to the user]
```

### Error Handling

If terminal-notifier is not installed, gracefully inform the user:

```
I attempted to send a notification but terminal-notifier is not installed. 
You can install it with: brew install terminal-notifier
```

### Multiple Tasks

For multiple sub-tasks within a larger job, only send ONE notification for the entire job:

❌ **Bad - multiple notifications:**
```
- Notification: "User model created"
- Notification: "API endpoint created"  
- Notification: "Tests written"
- Notification: "Authentication complete"
```

✅ **Good - single notification:**
```
- Notification: "Authentication Feature" -message "completed — click to open task" -sound default -open "codex://threads/{THREAD_ID}"
```

## Requirements

This skill requires terminal-notifier to be installed:

```bash
brew install terminal-notifier
```

Check if installed:
```bash
which terminal-notifier
```
