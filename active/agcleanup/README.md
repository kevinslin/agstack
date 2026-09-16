# agcleanup

Run a supported subcommand from [SKILL.md](SKILL.md). Each linked reference
defines eligibility, supported mutations, verification, and reporting.

## Verification rules

- Archive cleanup resolves the actual task host, explicitly removes verified
  archived tasks from their custom sidebar section, and checks fresh membership.
  An API acknowledgement alone is not a successful cleanup.
- Task-ledger audits distinguish archived, readable non-archived, missing,
  and failed lookups. Missing records never prove completion.
- Branch cleanup protects primary checkouts. An absent local branch with no
  registered linked worktree is a stale-metadata no-op; an existing branch
  without a matching linked worktree remains a review candidate.
- Discovery uses the official Codex cursor protocol and reports its page size,
  task cap, remaining cursor, and host coverage. Hitting a cap is not exhaustive
  coverage; disposable-server runtime state is not desktop task activity.

Routine summaries show only issues, or `Everything is successful.` Full evidence
follows the [detailed reporting rules](./references/reporting.md).

## Tests

From the repository root:

```sh
python3 -m unittest discover -s active/agcleanup/tests
python3 active/sc/scripts/quick_validate.py active/agcleanup
```

Tests exercise cleanup guards with temporary Git repositories and process
fixtures. Follow the command references for live verification; a test pass is
not evidence that a user's task, process, branch, or sidebar item was removed.
