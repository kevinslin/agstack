# agtask hosted Site

This directory is the canonical source for the private agtask dashboard and
task API hosted on Codex Sites. It lives beside the agtask CLI so dashboard,
backend, documentation, and tests can evolve together.

## Layout

- `app/page.tsx` and `app/tasks/[session]/page.tsx` render the dashboard and
  task-detail pages.
- `public/app.css`, `public/app.js`, and `public/task.js` mirror the local
  agtask dashboard's browser assets.
- `app/api/agtask/v1/operations/[operation]/route.ts` serves authenticated CLI
  operations; `app/api/dashboard` and `app/api/tasks` serve authenticated
  browser requests.
- `db/agtask.ts`, `db/dashboard.ts`, and `db/schema.ts` own hosted task
  operations, dashboard projections, and D1 schema definitions.
- `drizzle/` contains the D1 migrations included with each Site deployment.
- `.openai/hosting.example.json` documents the private Site linkage and logical
  `DB` binding. Copy it to the ignored `.openai/hosting.json`, set your own
  project identifier, and never put credentials in either file.

## Development

Run commands from this directory:

```sh
cp .openai/hosting.example.json .openai/hosting.json
# Set project_id in .openai/hosting.json to your private Site project.
npm install
npm test
npm run build
```

`npm test` builds the production Worker and exercises the dashboard, browser
authentication, machine API, and D1 persistence against a real local D1
runtime. Generate a migration after changing the hosted schema:

```sh
npm run db:generate
```

## Authentication and deployment

The private Site authenticates browser visitors through the Sites sign-in
gate. CLI requests require both the Sites bypass credential and the independent
application bearer validated against the hosted `AGTASK_TASKS_SECRET`.
`AGTASK_PROBE_SECRET` remains limited to the legacy synthetic probe endpoint.
Keep both runtime secrets in Sites configuration and local credentials outside
the repository; `.env.example` contains placeholders only.

Deploy only the validated contents of this directory to the Site's managed
source repository. Build the project, push its exact source revision with a
short-lived Sites source credential, package the generated output and D1
migrations, and save and privately deploy the resulting Site version. Do not
publish the parent repository or unrelated Git history to the managed source
remote.
