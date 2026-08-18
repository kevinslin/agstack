# Authenticated hosted backend

Read this reference only when the user requests durable state, authenticated
API endpoints, or local programmatic reads/writes.

## Choose the data authority

Declare whether local persistence remains authoritative, hosted D1 becomes
authoritative, or an explicitly designed projection connects them. Never claim
automatic synchronization or silently write to the wrong backend.

Declare a D1 binding in `.openai/hosting.json`:

```json
{
  "project_id": "existing-site-project-id",
  "d1": "DB",
  "r2": null
}
```

Define only required hosted tables. Generate and inspect D1 migrations before
deployment. D1 is not a user's local SQLite file: do not assume local migration
history, WAL settings, backups, FTS support, or filesystem semantics transfer.

Use parameterized SQL and atomic D1 batches for multi-record mutations:

```ts
import { env } from "cloudflare:workers";

await env.DB.batch([
  env.DB.prepare("INSERT INTO items (id, title) VALUES (?, ?)").bind(id, title),
  env.DB.prepare("INSERT INTO events (item_id, kind) VALUES (?, ?)")
    .bind(id, "created"),
]);
```

## Keep browser and machine access separate

The private Sites access gate protects browser visitors. Browser data routes
must additionally verify the server-forwarded user identity:

```ts
const userId = request.headers.get("oai-authenticated-user-id");

if (!userId?.trim()) {
  return Response.json({ error: "Authentication required" }, { status: 401 });
}
```

Require exact same-origin `Origin` validation for browser writes. Never send a
machine credential to browser JavaScript, HTML, query strings, or logs.

Private machine requests require two independent headers:

```http
OAI-Sites-Authorization: Bearer <sites-bypass-token>
Authorization: Bearer <application-token>
Content-Type: application/json
Idempotency-Key: <stable-mutation-id>
```

The Sites platform consumes the first credential before request dispatch. The
server route independently checks the second against a hosted secret such as
`APP_API_SECRET`, preferably using a constant-time comparison. A bypassed
request is identity-less; do not require browser user headers on machine API
routes or assume the platform authorization header reaches application code.

Generate the Sites bypass token only after the user explicitly requests it.
Generation rotates and immediately invalidates the existing credential. Reuse
an approved existing token when available; never generate one opportunistically.

Generate the application credential using a cryptographically secure random
source. Set it as a hosted secret before deployment; changing hosted runtime
secrets requires redeployment. Never print either secret.

## Local credential and request contract

Keep nonsecret configuration separate from credentials:

```json
{
  "backend": {
    "mode": "sites",
    "sites": {
      "url": "https://example.openai.chatgpt.site",
      "project_id": "site-project-id",
      "credential_ref": "file:/absolute/path/to/private-credentials.json"
    }
  }
}
```

Store credentials outside the repository in an owner-only `0600` regular file:

```json
{
  "bypass_token": "SITES_BYPASS_TOKEN",
  "app_token": "APPLICATION_API_TOKEN"
}
```

Reject symlinks, wrong ownership, permissive modes, missing tokens, and
unexpected credential fields. Environment variables are an alternative when
they reach every process that needs them; a child process cannot change its
parent's environment.

For each local API call:

1. Require HTTPS and the exact configured Site origin.
2. Send both bearer headers.
3. Bound request/response sizes and network timeouts.
4. Disable redirects so credentials never follow another origin.
5. Use a stable idempotency key for mutations and reuse it after ambiguity.
6. Redact credentials, prompts, and sensitive payloads from errors and logs.
7. Fail closed without silently writing to another persistence backend.

For hooks or callbacks, leave time within their actual execution deadline and
define whether unavailability fails open, queues a sanitized retry, or blocks.

## Mutation and privacy guarantees

- Validate exact request fields, types, bounds, and permitted transitions.
- Reject duplicate JSON keys and ambiguous selectors.
- Require optimistic revisions or expected statuses; return `409` on conflict.
- Make bulk operations atomic, including lifecycle/event records.
- Treat repeated matching event identities as idempotent.
- Redact descriptions, transcripts, absolute file paths, and identities by
  default; get explicit approval before publishing sensitive content.
- Use D1 for metadata and R2 for file bytes only when uploads were explicitly
  requested and the R2 binding, compensation, and cleanup are implemented.

## Required proof

Prove anonymous rejection, wrong application bearer rejection, identity-less
browser-route rejection, same-origin browser writes, valid dual-authenticated
machine writes, idempotent replay, stale-write conflict, and a real hosted
record visible in the Site. Reconcile ambiguous requests before retrying; never
create duplicate proof records blindly.
