# Core documentation hygiene

## Contents

- [Document lifecycle](#document-lifecycle)
- [Universal technical writing](#universal-technical-writing)
- [One-off functions](#one-off-functions)

## Document lifecycle

When a design or implementation change invalidates a current flow, guide,
reference, or architecture doc, update that document in the same pass or mark
it stale/superseded immediately.

Do not update an old spec to match a later invariant. A spec becomes historical
after its implementation ships or a newer spec or decision supersedes it.
Preserve that spec as the record of the design at that time. Document the new
invariant in the current owning reference, flow, decision, or changelog instead.
An active spec for work that has not shipped may still change with the design.

Do not leave contradictory current docs side by side. A stale current doc is
active misinformation for the next agent or reader; a historical spec is not
current guidance.

Preferred responses when a related doc is no longer accurate:
- Update it in the same change.
- If a full update is not practical yet, add a short stale-warning or
  superseded note that points to the newer source of truth.
- If a non-spec doc is purely historical, move or rename it so current guidance
  and legacy guidance are clearly separated.
- If an old spec differs from the new invariant, leave the spec unchanged and
  record the difference in a current document.

## Universal technical writing

Apply these rules to specifications, developer documentation, reviews, and other
durable technical writing.

### Make every sentence earn its place

Keep text that helps the reader decide, act, or understand a necessary boundary.
Delete repeated background, meta-commentary, and unrelated detail.

- **Bad:** "It is important to note that write requests are not retried."
- **Good:** "The client does not retry writes."

### Define concepts operationally

At first use, identify an unfamiliar concept by its relevant kind, owner or
caller, action, and observable role. Replace abstract verbs with the actual
operation when the distinction matters.

- **Bad:** "The controller reconciles the environment and dispatches work."
- **Good:** "The controller compares the saved configuration with the running
  service, then asks the worker to start, update, or stop instances."

### Use one term per concept

Repeat one established name. If two names denote different concepts, define
their boundary instead of using them interchangeably.

- **Bad:** "The API returns a `workspace_id`. Pass the project ID to
  `/workspaces/{id}`."
- **Good:** "The API returns a `workspace_id`. Pass the workspace ID to
  `/workspaces/{id}`."

### State the exact scope

Treat `all`, `every`, `only`, `never`, `centralized`, and `standardized` as
literal claims, not emphasis. Name the surface or boundary to which each claim
applies.

- **Bad:** "All requests go through the gateway."
- **Good:** "Authenticated `/api/*` requests go through the gateway; `/healthz`
  does not."

### Define canonical truth once

Keep each contract, field list, default, and behavior in one owning document.
Other documents may link to it and explain a local consequence, but must not
create a second definition.

- **Bad:** "The setup guide copies the API timeout table and changes the upload
  timeout to 60 seconds."
- **Good:** "The API reference defines request timeouts. Uploads use that
  timeout without overriding it."

### Re-baseline against current evidence

Before editing or reviewing, reread the current source and relevant diff. Retire
resolved findings. Preserve explicit keep, skip, and reject decisions unless the
evidence or requirements change.

- **Bad:** "Restore `legacy_mode` because an older review requested it."
- **Good:** "The current revision defers `legacy_mode`; no change is required."

### Make review findings self-contained

Cite the conflicting or excessive material, explain its consequence, identify
the failed rule, and give the smallest correction. Separate correctness issues
from optional polish.

- **Bad:** "The setup section is confusing."
- **Good:** "The required-input description and runnable example conflict: the
  setup section calls `--project` optional, but the example fails without it.
  Mark the flag required and add it to the command."

### Make diagrams literal

Use boxes for actors, resources, and components; nesting or labeled regions for
containment and boundaries; and labeled arrows for interactions or data flow.

- **Bad:** "Label the API-to-worker arrow `Project`."
- **Good:** "Draw `Project` as a containing region and label the API-to-worker
  arrow `starts job`."

## One-off functions

Minimize one-off helper functions. Before adding one, check whether the logic can
stay local, be expressed clearly inline, or reuse an existing shared helper.

If a helper is used by multiple modules, extract it into a general utility
library that other files can import instead of duplicating similar
implementations.

Add common helpers to a utility folder and split helpers into focused modules
grouped by common functionality.

Do not let a generic utility area become a dumping ground for unrelated code.
Only move helpers there when they are genuinely shared or clearly belong to a
reusable utility grouping.
