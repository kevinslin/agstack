# Private Sites deployment

Use the current `$sites-hosting` workflow and connector descriptions. Do not
invent a public Sites management API or manually handle unrelated Codex auth.

## Preserve project and secret boundaries

- Reuse the existing Site project, access policy, logical bindings, and hosted
  secrets when updating a deployed application.
- Create a new Site only when no intended project already exists.
- Keep `.openai/hosting.json` limited to `project_id`, `d1`, and `r2`.
- Never put source-repository credentials or API bearer tokens in Git remotes,
  repository files, package archives outside intended runtime configuration,
  command output, or user-visible logs.
- A temporary Sites managed-source write credential is distinct from both the
  private-access bypass token and the application API token.

## Publish the exact validated source

1. Build the Site and run focused executable tests.
2. Generate and inspect migrations if hosted database definitions changed.
3. Commit the exact Site source to its isolated managed-source history without
   pushing unrelated parent-repository files or history.
4. Obtain or reuse a short-lived Sites source-repository write credential. Push
   with a per-command HTTP authorization header; never persist the credential
   in Git configuration or embed it in a remote URL.
5. Package the production Worker output, static assets, hosting metadata, and
   migrations using the current Sites packaging helper.
6. Save a Site version for the exact pushed commit and packaged archive.
7. Deploy privately. If only shared/public deployment is available, ask the user
   to approve the exact audience before proceeding.
8. Poll deployment status until success or a concrete terminal failure.
9. Reopen the deployed Site in its existing browser tab when available.

## Verify the real deployment

After deployment, verify the user-visible page matches the original HTML
instead of stale cached content. For authenticated applications, create or
update an approved record through the local client, confirm the hosted backend
persisted it, and check that the private dashboard displays the same record.

Do not claim success from a submitted deployment, successful build, local mock,
unverified URL, or connector update alone.
