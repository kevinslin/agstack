---
name: html2site
description: Convert an existing static HTML site into a private Codex Site, optionally adding a persistent authenticated API and local programmatic writes. Use only when deliberately invoked as $html2site.
dependencies:
  - sites-building
  - sites-hosting
---

# html2site

Use only when the user explicitly invokes `$html2site`. An ordinary request to
build, host, redesign, or edit a website does not activate this skill.

Convert an existing local HTML application into a Codex Site while preserving
its user-visible design. Add D1-backed, authenticated server endpoints only
when the user requests shared state, a backend API, or local programmatic
access.

## Intake

1. Resolve the actual source HTML, stylesheet, JavaScript, assets, routes, and
   existing API or persistence contracts. Ask only when the intended source or
   data authority cannot be determined safely.
2. Choose the smallest requested deployment shape:
   - **Static:** HTML, styles, scripts, assets, and private hosting.
   - **Application:** static conversion plus hosted D1, browser routes, and an
     authenticated machine API when local writes are requested.
3. Keep the canonical Site under the existing project, normally `./site/`.
   Never create a nested Git repository or publish unrelated parent-repository
   source, history, local databases, or credentials.
4. Apply `$sites-building` before implementation and `$sites-hosting` after a
   successful build. Preserve an existing Site project and access policy.

## Workflow

1. Read [static conversion](./references/static-conversion.md). Preserve the
   original DOM, relative URLs, browser interactions, assets, and responsive
   behavior. Explicitly force dynamic rendering when page content can change.
2. When the user requests an authenticated API, persistent data, shared state,
   or local writes, also read [authenticated backend](./references/authenticated-backend.md).
   Separate browser identity from machine authentication, declare only required
   D1/R2 bindings, and keep secrets outside source control.
3. Build and exercise the exact requested experience. Use realistic synthetic
   records unless the user authorizes creating real data. Do not report a
   successful local write until the deployed API and hosted interface both
   confirm the same record.
4. Read [private deployment](./references/private-deployment.md). Publish the
   validated Site privately unless the user explicitly requests local-only work
   or approves a different audience.

## Non-negotiable boundaries

- Preserve the source HTML design; do not substitute a generic dashboard.
- Keep `.openai/hosting.json` limited to `project_id` and logical `d1`/`r2`
  bindings. Never store bearer tokens or runtime secret values there.
- A private machine API requires **both** a Sites bypass credential and an
  independently verified application credential. Never expose either to
  browser JavaScript.
- Generate or rotate a Sites bypass token only when the user explicitly asks
  for one. Rotation immediately invalidates the previous token.
- Never treat a private Site as public merely to make automated calls work.
- Disable unsupported uploads; configure R2 explicitly before accepting files.
- Preserve existing local persistence unless the user deliberately selects or
  migrates to a hosted authoritative backend. Never silently fall back or
  synchronize data across stores.
- Never run `npm run precommit`.

## Completion

Return the deployed private URL, canonical Site source location, supported
browser/API behavior, and any remaining unsupported capability. Mention token
or deployment internals only when the user asks or needs to take action.
