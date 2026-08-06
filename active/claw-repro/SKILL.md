---
name: claw-repro
description: Reproduce and fix OpenClaw issues with Showboat proof, managed implementation, and repo-local integration gateways.
dependencies: [mem, showboat, sw-ctrl]
---

# claw-repro

Use this skill when the user asks to reproduce an OpenClaw bug, drive the fix, and prove the result through the repo-local integration Gateway workflow.

## Contract

Complete the work in this order:

1. Reproduce the issue with `$showboat`.
2. Use `$sw-ctrl` to create a feature spec and write the fix.
3. Write the feature spec inside OpenClaw `$mem` under the aggregate `claw` base.
4. Prove the fixed behavior with `$showboat` using a fresh integration Gateway.
5. Push changes and babysit pr

Do not skip the repro proof unless the issue cannot be reproduced after concrete attempts; in that case, write the failed repro evidence and stop before making speculative code changes.

## OpenClaw Setup

Default repo root is `/Users/kevinlin/code/openclaw` unless the user provides a different checkout.

Before launching an integration Gateway, read the repo-local integration guide:

```bash
sed -n '1,220p' .mem/integ/README.md
```

Run OpenClaw integration commands from the repo root. The local helpers are expected under:

```text
.mem/integ/scripts/
```

Use the helpers rather than changing normal `~/.openclaw` state.

## Artifact Roots

Resolve canonical artifact roots before creating any spec, proof, or Showboat document. Start from the OpenClaw repo root, read `.mem.yaml` when it exists, and honor active workspace or prep instructions that override the memory root.

Use the aggregate `claw` memory base for issue specs and proof documents unless the user or workspace instructions explicitly select another base. Its canonical root is `/Users/kevinlin/code/openclaw/.mem/main`; for OpenClaw AGD work this normally means:

```text
.mem/main/flow/<issue-or-feature-slug>.md
.mem/main/integ/<issue-or-feature-slug>-repro.md
.mem/main/integ/<issue-or-feature-slug>-fixed.md
```

Only use `.mem/integ/proofs/` when the active workspace instructions explicitly choose integration-local proofs. In sparse or temporary worktrees, write or copy final artifacts to the durable canonical OpenClaw memory root `/Users/kevinlin/code/openclaw/.mem/main` before handoff.

After writing artifacts, verify the final paths with `ls -l` and check that links or path references inside the flow and proof docs point at the same canonical locations.

## Random Gateway Ports

Always start Gateways on an explicit random high port. Other tests may be running concurrently, so never rely on the default port.

Choose a port immediately before setup:

```bash
python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
```

Pass that port to both workspace setup and Gateway launch:

```bash
./.mem/integ/scripts/setup_tmp_integ_workspace.mjs <ws-name> --port <port>
./.mem/integ/scripts/run_integ_gateway.mjs <ws-name> <port>
```

Use a new workspace name for the before-fix repro and another new workspace name for the after-fix proof unless preserving state is essential to the bug. If state must be preserved, document that choice in the Showboat note.

## Repro Proof

Use `$showboat` for the live repro artifact under the canonical proof directory resolved above. Keep raw nondeterministic output in a sibling `.raw.md` or raw text file, then capture stable summaries in the verified Showboat document.

The repro proof should include:

- issue summary and expected versus actual behavior
- integration workspace name and selected Gateway port
- exact OpenClaw commands or Gateway requests used to trigger the issue
- deterministic pass/fail summary showing the bug
- `uvx showboat verify <file>` result

Do not use Showboat as a wrapper around existing unit tests. Use it to exercise the real integration behavior.

## Spec And Fix

Use `$sw-ctrl` for the managed implementation phase. Keep the immediate blocker local, then delegate independent docs, code, or review work when useful.

The feature spec must be written through `$mem` from the OpenClaw repo root. Target the aggregate `claw` base unless the user says otherwise. Prefer a focused spec path under the canonical artifact root resolved above, such as:

```text
flow/<issue-or-feature-slug>.md
```

The spec should capture:

- repro evidence and proof artifact path
- current behavior and desired behavior
- affected code paths
- implementation plan
- validation plan using the integration Gateway
- unresolved risks or non-goals

Keep code changes scoped to the issue. Preserve unrelated dirty worktree changes.

## Fixed Proof

After the fix, create a fresh integration workspace and random Gateway port, then use `$showboat` again to prove the behavior is fixed through the integration Gateway.

The fixed proof should include:

- link or path to the feature spec
- changed behavior exercised through the new Gateway
- deterministic evidence that the original failure no longer occurs
- any focused tests run outside Showboat
- `uvx showboat verify <file>` result

Completion requires the repro artifact, feature spec, code fix, and fixed proof to be present or a clear blocker explaining why one of those deliverables could not be completed.

## Push changes and babysit

After proof is established, trigger:push-pr
