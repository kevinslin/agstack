# Codex Site Authenticated API Probe

Date: 2026-08-06.

Status: verified. An explicitly authorized Sites bypass token and a separate
application bearer secret successfully updated a private owner-only Site
through a programmatic HTTP request without redeployment.

## Site and source

- Deployed owner-only Site:
  [agtask authenticated API probe](https://agtask-api-probe-msi0lmww.openai.chatgpt.site).
- Project ID: `appgprj_6a74f9c7d61c8191a037dc4756ce4eff`.
- Access mode: `custom`, with exactly one explicitly allowed owner and no
  allowed groups.
- Saved version: `1`.
- Deployment ID: `appgdep_6a74fb0960048191934d3a2bbe5c92e6`.
- Source commit: `a65e43e6430eb550236674ef9d52319fe3d3c8f1`.
- Runtime secret name: `AGTASK_PROBE_SECRET`; value is managed as a Sites
  secret and is not recorded here.
- Hosted storage: Sites-managed D1 binding `DB`, with a synthetic single-row
  `probe_state` schema.
- Source was committed and pushed from an isolated Site repository; no agtask
  application source was deployed.

The deployed application offers `GET /api/probe` and `POST /api/probe`. A
successful `POST` requires the app-specific bearer secret, validates a bounded
synthetic JSON message, and updates the D1 row. Responses can report whether a
workspace user identity or the Sites platform-authorization header reached the
application without disclosing either header's value.

The read-only Sites database connector initially verified that the production
`DB` binding exists, the `probe_state` migration was applied, and the table
contained zero rows. After the authorized request, an independent D1 read
confirmed exactly one row containing the submitted synthetic value.

## Verified external request matrix

| Programmatic request | HTTP status | Content type | Interpretation |
| --- | --- | --- | --- |
| `GET /api/probe` with no authentication | `401` | `text/html` | Sites private dispatch denies access before the route. |
| `POST /api/probe` with no authentication | `401` | `text/html` | Sites private dispatch denies access before the route. |
| `POST /api/probe` with only the valid app bearer secret | `401` | `text/html` | The app secret does not satisfy the private Sites gate. |
| `POST /api/probe` with a fabricated Sites token plus the valid app bearer secret | `401` | `text/html` | An invalid platform bearer token does not bypass the private gate. |
| `POST /api/probe` with only the valid Sites bypass token | `401` | `application/json` | The private gate is bypassed, but the application rejects the missing app secret. |
| `POST /api/probe` with the valid Sites bypass token plus an incorrect app secret | `401` | `application/json` | Application authorization remains independent of Sites dispatch. |
| `GET /api/probe` with the valid Sites bypass token | `200` | `application/json` | The owner-only private policy accepts the explicitly authorized machine bearer token. |
| `POST /api/probe` with both valid credentials | `200` | `application/json` | The synthetic value is durably written to Sites-managed D1. |
| Subsequent authenticated `GET /api/probe` | `200` | `application/json` | The same synthetic value is returned from D1. |
| Authenticated `GET /` | `200` | `text/html` | The deployed page renders the updated D1 value without redeployment. |

The authorized platform token was generated exactly once after explicit user
approval. Neither it nor the application secret was printed or persisted in the
source repository or this report. No real ledger data or user information was
sent to the Site.

## Verified machine-authentication flow

The Sites connector required a direct user request before invoking
`sites_generate_siwc_bypass_token`. After that explicit authorization, it
generated one Site-specific machine token. Its tool contract says subsequent
generation would immediately rotate and invalidate the existing token.

The successful programmatic request used:

```http
POST /api/probe HTTP/1.1
Host: agtask-api-probe-msi0lmww.openai.chatgpt.site
OAI-Sites-Authorization: Bearer <explicitly-approved-site-bypass-token>
Authorization: Bearer <existing-private-application-secret>
Content-Type: application/json

{"message":"synthetic-authenticated-update-msi27g76"}
```

The application returned HTTP `200` with:

```json
{
  "probe": {
    "message": "synthetic-authenticated-update-msi27g76",
    "updatedAt": "2026-08-06T22:00:17.400Z"
  },
  "identityPresent": false,
  "platformHeaderForwarded": false
}
```

Three independent checks matched the same message: the authenticated API
read-back, the rendered deployed page, and the connector's read-only D1 table
inspection. The deployment version did not change.

`identityPresent: false` confirms that bypass requests do not acquire a human
workspace identity. `platformHeaderForwarded: false` confirms that Sites
consumes `OAI-Sites-Authorization` before invoking this Worker. Therefore
application authorization must use a separate credential such as the
independent `Authorization: Bearer <application-secret>` header.

This result proves machine-authenticated ingress under the observed `custom`
policy containing exactly one owner and no groups. Workspace-wide, multi-user,
and group-based policies were not tested; token lifetime, revocation,
rotation overlap, audit visibility, and access under those other policies
remain undocumented.

## Related specifications

- [Authoritative local/Sites backend-mode design](specs/2026-08-06-agtask-sites-backend-mode-design.md)
- [Superseded dashboard projection research](CODEX_SITE_DASHBOARD_SPEC.md)
- [Official Codex Sites documentation](https://developers.openai.com/codex/sites)
