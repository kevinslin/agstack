import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the real hosted agtask dashboard", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>agtask dashboard<\/title>/i);
  assert.match(html, /<h1>agtask dashboard<\/h1>/i);
  assert.match(html, /id="view-tabs"/);
  assert.match(html, /id="search"/);
  assert.match(html, /id="groups"/);
  assert.match(html, /src="\/app\.js"/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});

test("keeps the dashboard and task detail dynamically rendered", async () => {
  const [dashboard, taskDetail, dashboardClient, taskClient] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/tasks/[session]/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../public/app.js", import.meta.url), "utf8"),
    readFile(new URL("../public/task.js", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /export const dynamic = "force-dynamic"/);
  assert.match(taskDetail, /export const dynamic = "force-dynamic"/);
  assert.match(dashboard, /src="\/app\.js"/);
  assert.match(taskDetail, /src="\/task\.js"/);
  assert.match(dashboardClient, /api\/dashboard/);
  assert.match(taskClient, /api\/tasks/);
});
