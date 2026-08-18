# Static HTML conversion

Read this reference for every `$html2site` request.

## Inspect the actual application

Find the entry HTML, linked CSS, browser scripts, images, fonts, vendored
libraries, detail routes, form submissions, and fetch endpoints. If the source
is embedded in Python or another runtime, extract literal HTML/CSS/JavaScript
without importing or executing the application.

Record behavior that must survive conversion:

- Existing page titles, headings, landmarks, IDs, and data attributes.
- Keyboard shortcuts, filters, sorting, pagination, forms, and detail pages.
- Relative asset paths, route prefixes, and client-side request contracts.
- Current responsive layout, typography, colors, and visible content.
- Whether content is static, locally generated, or backed by a database.

Do not copy a local database, machine-specific paths, credentials, prompts, or
private user data merely because the HTML references them.

## Create the Site inside the project

Prefer this layout:

```text
project/
└── site/
    ├── .openai/hosting.json
    ├── app/page.tsx
    ├── app/layout.tsx
    ├── public/
    ├── package.json
    └── tests/
```

Use the current Sites starter and preserve its package manager, lockfile,
Worker-compatible build, and existing Site linkage. Reuse an existing `site/`
directory instead of creating a parallel project.

Transplant the original markup into `app/page.tsx`; preserve required element
IDs exactly. Place unchanged browser assets in `public/`. Create equivalent
detail pages and compatible API paths when the original client requests them.

Avoid a nested `.git` directory. If Sites requires a separate managed Git
history, store its Git metadata outside the canonical source tree or publish
an isolated export containing only the Site.

## Rendering and asset safety

Use dynamic rendering for dashboards, record details, identity-aware pages,
and any route whose output must change after deployment or database writes:

```ts
export const dynamic = "force-dynamic";
```

Set this on every affected page module. A previously deployed static page can
remain cached even after replacement JavaScript and CSS are already live.

Preserve safe text/Markdown rendering and URL-scheme filtering. Do not replace
sanitized DOM construction with untrusted `innerHTML`. Do not expose local
absolute paths, capability URLs, or app secrets in HTML or bundled assets.

When a local feature requires unavailable hosted infrastructure, hide or
disable its control and return an explicit error from its API route. Do not
advertise nonfunctional upload or mutation controls.

## Validate

- The production build succeeds.
- The original recognizable layout, controls, and client assets are present.
- Original client-side routes resolve without changing their payload shape.
- Dynamic pages do not reuse stale deployment HTML.
- No credentials or sensitive local data appear in rendered HTML or assets.
