# Task Completion Notifier Skill

A generic agent skill that sends desktop notifications when tasks are complete using terminal-notifier.

## Overview

This skill enables a root task to notify you via desktop notifications when a job is finalized, needs input, or ends in errors. By default, jobs assigned directly to the root task trigger one notification at final handoff unless you say otherwise. Subtasks never notify unless you explicitly request a notification for that specific subtask.

## Installation

This skill requires `terminal-notifier` to be installed on macOS:

```bash
brew install terminal-notifier
```

Verify installation:
```bash
which terminal-notifier
```

## Usage

The skill is automatically invoked when:

1. You explicitly ask to be notified ("notify me when done")
2. The agent completes a long-running task
3. The agent needs your input to proceed
4. The agent encounters errors that block progress

### Automatic Behavior

By default, assume jobs assigned directly to the root task will generate exactly one notification. The agent should send it only after the work is fully finalized and immediately before the final user-facing report.

### Agent Scope

Only the root task that owns the overall job should send a notification. Subtasks, subagents, delegated workers, review workers, and background worker agents should report their terminal state to the root task instead of sending a notification themselves.

A separate Codex task created as an `agtask` child is a subtask for notification purposes even when it is user-owned or otherwise considers itself top-level. Detect it from an `<agtask-bootstrap version="2">` creation envelope or verified agtask ledger metadata with `kind: child` or a non-null `parent_session_id`. A general instruction to use this skill does not override this suppression; the user must explicitly request a notification for that specific subtask.

### Timing Rule

Use this skill only at the very end of the job unless the user explicitly asks for different timing.

Order:

1. Finish the work
2. Verify and finalize the outcome
3. Send the notification
4. Deliver the final report

### Notification Format

```bash
terminal-notifier -title "{JOB_DESCRIPTION}" -message "{STATUS}"
```

**Status values:**
- `completed` - Task finished successfully
- `needs_input` - Task requires user input
- `errors` - Task encountered errors

## Examples

### Request with Explicit Notification

```
User: "Implement the user dashboard and notify me when you're done"
```

The agent will complete the work, finalize the result, send the notification, and then deliver the final report:
```bash
terminal-notifier -title "User Dashboard Implementation" -message "completed"
```

### Long-Running Task (Automatic Notification)

```
User: "Run the full test suite and fix any failures"
```

The agent will execute tests, attempt fixes, finalize the outcome, send the notification, and then deliver the final report:
```bash
terminal-notifier -title "Test Suite and Fixes" -message "completed"
```

### Needs Input

```
User: "Set up authentication"
```

If the agent needs to choose between OAuth or JWT, it first confirms it is blocked, then sends:
```bash
terminal-notifier -title "Authentication Setup" -message "needs_input"
```

### Encountered Errors

```
User: "Deploy to production"
```

If deployment fails and the agent has reached a finalized error state:
```bash
terminal-notifier -title "Production Deployment" -message "errors"
```

## Features

- **Automatic notifications** - Default behavior for all jobs unless disabled
- **Clear status indicators** - completed, needs_input, or errors
- **Concise titles** - Understand what finished at a glance
- **Final-handoff timing** - Sent only after work is finalized and right before the final report
- **No spam** - One notification per task, not per step
- **Root-task ownership** - Subtasks report state upward; only the root task sends the single final notification

## Configuration

No configuration needed. The skill is ready to use once terminal-notifier is installed.

## Disabling Notifications

If you don't want notifications for a specific task, tell the agent:

```
User: "Run tests but don't notify me"
```

## Troubleshooting

### Notification not appearing

1. Check terminal-notifier is installed: `which terminal-notifier`
2. Test manually: `terminal-notifier -title "Test" -message "Hello"`
3. Check macOS notification settings for Terminal

### Permission issues

Ensure Terminal has notification permissions:
1. System Preferences → Notifications
2. Find Terminal (or your terminal app)
3. Enable "Allow Notifications"

## Version

Current version: 1.2.2
