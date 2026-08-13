import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { Miniflare } from "miniflare";

const taskSecret = "unit-test-task-secret";
const probeSecret = "unit-test-probe-secret";
const serverRoot = new URL("../dist/server/", import.meta.url).pathname;
const compiledFiles = await readdir(serverRoot, {
  recursive: true,
  withFileTypes: true,
});
const modules = [
  { type: "ESModule", path: join(serverRoot, "index.js") },
  ...compiledFiles
    .filter((entry) => entry.isFile() && entry.name.endsWith(".js"))
    .map((entry) => join(entry.parentPath, entry.name))
    .filter((path) => path !== join(serverRoot, "index.js"))
    .map((path) => ({ type: "ESModule", path })),
];
const service = new Miniflare({
  compatibilityDate: "2026-05-22",
  compatibilityFlags: ["nodejs_compat"],
  modules,
  modulesRoot: serverRoot,
  d1Databases: ["DB"],
  bindings: {
    AGTASK_TASKS_SECRET: taskSecret,
    AGTASK_PROBE_SECRET: probeSecret,
  },
  serviceBindings: {
    ASSETS: async (request) => {
      const pathname = new URL(request.url).pathname;
      const contentTypes = new Map([
        ["/app.css", "text/css; charset=utf-8"],
        ["/app.js", "application/javascript; charset=utf-8"],
        ["/task.js", "application/javascript; charset=utf-8"],
        ["/vendor/marked.js", "application/javascript; charset=utf-8"],
      ]);

      if (!contentTypes.has(pathname)) {
        return new Response("Not found", { status: 404 });
      }

      try {
        const asset = await readFile(new URL(`../public${pathname}`, import.meta.url));
        return new Response(asset, {
          headers: { "content-type": contentTypes.get(pathname) },
        });
      } catch (error) {
        if (error.code === "ENOENT") {
          return new Response("Not found", { status: 404 });
        }
        throw error;
      }
    },
  },
});

test.after(async () => {
  await service.dispose();
});

const setup = (async () => {
  const d1 = await service.getD1Database("DB");

  for (const filename of [
    "../drizzle/0000_ambitious_korg.sql",
    "../drizzle/0001_glorious_justin_hammer.sql",
  ]) {
    const migration = await readFile(new URL(filename, import.meta.url), "utf8");

    for (const statement of migration.split("--> statement-breakpoint")) {
      if (statement.trim()) {
        await d1.prepare(statement.trim()).run();
      }
    }
  }
})();

async function operation(name, payload, token = taskSecret) {
  await setup;

  return service.dispatchFetch(
    `https://agtask.local/api/agtask/v1/operations/${name}`,
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    },
  );
}

async function browser(
  path,
  { identity = true, origin, body, rawBody, method = "GET" } = {},
) {
  await setup;

  return service.dispatchFetch(`https://agtask.local${path}`, {
    method,
    headers: {
      ...(identity ? { "oai-authenticated-user-id": "user-hosted-dashboard-test" } : {}),
      ...(origin === undefined ? {} : { origin }),
      ...(body === undefined && rawBody === undefined
        ? {}
        : { "content-type": "application/json" }),
    },
    ...(rawBody === undefined
      ? body === undefined
        ? {}
        : { body: JSON.stringify(body) }
      : { body: rawBody }),
  });
}

function fixtureTask(sessionId, id, status = "active") {
  return {
    ...mainTask,
    id,
    session_id: sessionId,
    title: `Hosted dashboard ${sessionId}`,
    status,
  };
}

const mainTask = {
  id: "a10bf864-c377-450f-8818-437dfb644a01",
  session_id: "test-main-session",
  parent_session_id: null,
  kind: "main",
  project: "sites-smoke",
  title: "Hosted test task",
  description: "Verify the hosted agtask backend.",
  initial_prompt: "Verify the hosted agtask backend.",
  status: "active",
};

test("both built dashboard page modules force dynamic rendering and bypass stale deployment caches", async () => {
  const pages = await Promise.all(
    compiledFiles
      .filter((entry) => entry.isFile() && /^page-.*\.js$/.test(entry.name))
      .map(async (entry) => ({
        name: entry.name,
        source: await readFile(join(entry.parentPath, entry.name), "utf8"),
      })),
  );

  for (const [route, marker] of [
    ["/", "view-tabs"],
    ["/tasks/[session]", "detail-content"],
  ]) {
    const page = pages.find(({ source }) => source.includes(marker));
    assert.ok(page, `production build must contain the ${route} page module`);
    assert.match(
      page.source,
      /force-dynamic/,
      `${route} must force dynamic rendering to prevent prior-deployment HTML cache hits`,
    );
    assert.match(
      page.source,
      /export\s*\{[^}]*\bas\s+dynamic\b/,
      `${route} production module must export its dynamic rendering configuration`,
    );
  }
});

test("every task operation requires the separate task bearer", async () => {
  for (const name of ["health", "show", "list", "register", "dashboard"]) {
    assert.equal((await operation(name, {}, null)).status, 401);
    assert.equal((await operation(name, {}, probeSecret)).status, 401);
  }

  const response = await operation("health", {});
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    status: "ok",
    backend: "sites",
    schema_version: 1,
  });
});

test("registration and creation event persist atomically and replay idempotently", async () => {
  const invalidId = await operation("register", { ...mainTask, id: "not-a-uuid" });
  assert.equal(invalidId.status, 400);

  const response = await operation("register", mainTask);
  assert.equal(response.status, 200);
  const created = await response.json();
  assert.equal(created.id, mainTask.id);
  assert.equal(created.created.length > 10, true);
  assert.equal(created.task_created, true);
  assert.deepEqual(created.files, []);
  assert.equal(created.rollouts.length, 1);
  assert.equal(created.rollouts[0].turn_id, "thread.created");

  const replay = await operation("register", mainTask);
  assert.equal(replay.status, 200);
  const replayed = await replay.json();
  assert.equal(replayed.task_created, false);
  assert.equal(replayed.rollouts.length, 1);

  const conflict = await operation("register", {
    ...mainTask,
    title: "Conflicting task title",
  });
  assert.equal(conflict.status, 409);
});

test("hosted list applies created and updated ranges and rejects unsafe filters", async () => {
  const taskResponse = await operation("show", { id: mainTask.id });
  const task = await taskResponse.json();
  const day = task.created.slice(0, 10);
  const nextDay = new Date(`${day}T00:00:00.000Z`);
  nextDay.setUTCDate(nextDay.getUTCDate() + 1);
  const range = {
    start: `${day}T00:00:00.000Z`,
    end: nextDay.toISOString(),
  };

  const matching = await operation("list", {
    filters: [
      { field: "created", ...range },
      { field: "updated", ...range },
    ],
    limit: 1,
  });
  assert.deepEqual((await matching.json()).map((row) => row.id), [mainTask.id]);

  const excluded = await operation("list", {
    filters: [{ field: "created", start: range.end, end: "2099-01-01T00:00:00.000Z" }],
  });
  assert.deepEqual(await excluded.json(), []);

  for (const filters of [
    "created=today",
    [{ field: "closed", ...range }],
    [{ field: "created", start: range.start }],
  ]) {
    assert.equal((await operation("list", { filters })).status, 400);
  }
});

test("turns are idempotent, bounded, and drive blocked/active status", async () => {
  const event = {
    session_id: mainTask.session_id,
    role: "assistant",
    turn_id: "assistant-turn-1",
    content: "Blocked: waiting on the example dependency.",
  };

  const first = await operation("record-turn", event);
  assert.equal(first.status, 200);
  const blocked = await first.json();
  assert.equal(blocked.status, "blocked");
  assert.equal(blocked.rollouts.filter((row) => row.turn_id === event.turn_id).length, 1);

  const replay = await operation("record-turn", event);
  assert.equal(replay.status, 200);
  assert.equal((await replay.json()).rollouts.length, blocked.rollouts.length);

  const conflict = await operation("record-turn", {
    ...event,
    content: "A conflicting message for the same turn.",
  });
  assert.equal(conflict.status, 409);

  const oversized = await operation("append-rollout", {
    id: mainTask.id,
    role: "meta",
    turn_id: "oversized-event",
    message: "x".repeat(241),
  });
  assert.equal(oversized.status, 400);

  const user = await operation("record-turn", {
    id: mainTask.id,
    role: "user",
    turn_id: "user-turn-1",
    content: "Continue the hosted task.",
  });
  assert.equal((await user.json()).status, "active");
});

test("status transitions, reopen, search, dashboard, and browser use D1 state", async () => {
  const dropped = await operation("status", {
    id: mainTask.id,
    status: "drop",
  });
  assert.equal(dropped.status, 200);
  assert.ok((await dropped.json()).closed);

  const terminalConflict = await operation("status", {
    id: mainTask.id,
    status: "active",
  });
  assert.equal(terminalConflict.status, 409);

  const reopened = await operation("reopen", { id: mainTask.id });
  assert.equal((await reopened.json()).status, "active");

  const search = await operation("search", { query: "Hosted test", limit: 20 });
  assert.equal((await search.json())[0].id, mainTask.id);

  const dashboard = await operation("dashboard", {
    projects: [mainTask.project],
    parent_session_ids: [],
    include_root: false,
    statuses: [],
    sort_field: "updated",
    direction: "desc",
    search: "Hosted",
    view_id: null,
  });
  const snapshot = await dashboard.json();
  assert.equal(snapshot.visible_count, 1);
  assert.equal(snapshot.groups.find((group) => group.status === "active").count, 1);

  const page = await service.dispatchFetch("https://agtask.local/");
  assert.equal(page.status, 200);
  const html = await page.text();
  assert.match(html, /agtask dashboard/);
  assert.doesNotMatch(html, new RegExp(taskSecret));
  assert.doesNotMatch(html, new RegExp(probeSecret));
});

test("hosted root recreates the local dashboard controls and serves its actual client assets", async () => {
  const page = await browser("/");
  assert.equal(page.status, 200);
  const html = await page.text();

  assert.match(html, /<title>agtask dashboard<\/title>/i);
  assert.match(html, /LOCAL TASK LEDGER/);
  assert.match(html, /class="topbar"/);
  assert.match(html, /<h1[^>]*>agtask dashboard<\/h1>/i);

  for (const id of [
    "view-tabs",
    "search",
    "sort",
    "direction",
    "refresh",
    "filter-trigger",
    "filter-menu",
    "filter-menu-title",
    "filter-menu-back",
    "filter-menu-close",
    "filter-menu-search",
    "filter-menu-list",
    "filter-bar",
    "active-filters",
    "add-filter",
    "notice",
    "groups",
    "summary",
    "status-modal",
    "status-task-title",
    "status-close",
    "status-search",
    "status-options",
    "status-error",
    "attachment-picker",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`), `missing local dashboard control #${id}`);
  }
  assert.match(
    html,
    /<input[^>]*id="attachment-picker"[^>]*disabled(?:="")?[^>]*hidden/,
    "unsupported hosted file uploads must not expose an enabled local attachment picker",
  );

  for (const [path, contentType] of [
    ["/app.css", "text/css"],
    ["/app.js", "javascript"],
    ["/task.js", "javascript"],
    ["/vendor/marked.js", "javascript"],
  ]) {
    const response = await browser(path);
    assert.equal(response.status, 200, `${path} should be served by the hosted assets binding`);
    assert.match(response.headers.get("content-type") ?? "", new RegExp(contentType));
    assert.ok((await response.text()).length > 100, `${path} should contain the real client asset`);
  }

  const dashboardScript = await (await browser("/app.js")).text();
  assert.match(dashboardScript, /api\/dashboard/);
  assert.match(dashboardScript, /expected_status/);
});

test("browser dashboard and task detail require a forwarded user and expose real hosted D1 state", async () => {
  const taskPath = `/api/tasks/~${mainTask.session_id}`;

  assert.equal((await browser("/api/dashboard", { identity: false })).status, 401);
  assert.equal((await browser(taskPath, { identity: false })).status, 401);

  const dashboard = await browser(`/api/dashboard?project=${mainTask.project}&search=Hosted`);
  assert.equal(dashboard.status, 200);
  const snapshot = await dashboard.json();
  assert.deepEqual(snapshot.filters.projects, [mainTask.project]);
  assert.equal(snapshot.search, "Hosted");
  assert.ok(
    snapshot.groups.some((group) =>
      group.threads.some((thread) => thread.session_id === mainTask.session_id),
    ),
    "the task created through the real machine API must appear in the hosted browser dashboard",
  );
  assert.deepEqual(
    snapshot.groups.map((group) => group.status),
    ["todo", "active", "blocked", "merging", "done", "drop"],
  );

  const detail = await browser(taskPath);
  assert.equal(detail.status, 200);
  const task = await detail.json();
  assert.equal(task.id, mainTask.id);
  assert.equal(task.session_id, mainTask.session_id);
  assert.equal(task.title, mainTask.title);
  assert.ok(Array.isArray(task.rollouts));

  const detailPage = await browser(`/tasks/~${mainTask.session_id}`);
  assert.equal(detailPage.status, 200);
  const detailHtml = await detailPage.text();
  assert.match(detailHtml, /Task detail.*agtask/);
  for (const id of [
    "back-link",
    "detail-content",
    "task-title",
    "task-description",
    "timeline",
    "task-created",
    "task-updated",
    "task-session-id",
    "task-files-property",
    "task-files",
    "detail-notice",
  ]) {
    assert.match(detailHtml, new RegExp(`id="${id}"`), `missing local detail control #${id}`);
  }
});

test("single dashboard status writes require identity, same origin, and an unstale expected status", async () => {
  const task = fixtureTask(
    "browser-single-session",
    "a10bf864-c377-450f-8818-437dfb644a02",
  );
  assert.equal((await operation("register", task)).status, 200);
  const path = `/api/tasks/~${task.session_id}/status`;
  const body = { expected_status: "active", status: "done" };

  assert.equal(
    (await browser(path, { identity: false, origin: "https://agtask.local", method: "PATCH", body }))
      .status,
    401,
  );
  assert.equal((await browser(path, { method: "PATCH", body })).status, 403);
  assert.equal(
    (await browser(path, { origin: "https://untrusted.example", method: "PATCH", body })).status,
    403,
  );

  const stale = await browser(path, {
    origin: "https://agtask.local",
    method: "PATCH",
    body: { expected_status: "blocked", status: "done" },
  });
  assert.equal(stale.status, 409);
  assert.equal((await (await operation("show", { session_id: task.session_id })).json()).status, "active");

  const updated = await browser(path, {
    origin: "https://agtask.local",
    method: "PATCH",
    body,
  });
  assert.equal(updated.status, 200);
  const result = await updated.json();
  assert.equal(result.changed, true);
  assert.equal(result.task.status, "done");
  assert.equal(result.task.closed, result.task.updated);
  assert.equal(result.task.session_id, task.session_id);

  const detail = await (await operation("show", { session_id: task.session_id })).json();
  assert.equal(detail.status, "done");
  assert.equal(detail.closed, detail.updated);
  assert.equal(
    detail.rollouts.filter((rollout) => rollout.message === "status:active->done").length,
    1,
  );
});

test("bulk dashboard writes use the exact local payload and roll back every task on stale CAS", async () => {
  const first = fixtureTask(
    "browser-bulk-first",
    "a10bf864-c377-450f-8818-437dfb644a03",
    "todo",
  );
  const second = fixtureTask(
    "browser-bulk-second",
    "a10bf864-c377-450f-8818-437dfb644a04",
  );
  assert.equal((await operation("register", first)).status, 200);
  assert.equal((await operation("register", second)).status, 200);

  const path = "/api/tasks/status";
  const validBody = {
    tasks: [
      { session_id: first.session_id, expected_status: "todo" },
      { session_id: second.session_id, expected_status: "active" },
    ],
    status: "drop",
  };

  assert.equal(
    (
      await browser(path, {
        identity: false,
        origin: "https://agtask.local",
        method: "PATCH",
        body: validBody,
      })
    ).status,
    401,
  );
  assert.equal((await browser(path, { method: "PATCH", body: validBody })).status, 403);
  assert.equal(
    (
      await browser(path, {
        origin: "https://untrusted.example",
        method: "PATCH",
        body: validBody,
      })
    ).status,
    403,
  );

  const stale = await browser(path, {
    origin: "https://agtask.local",
    method: "PATCH",
    body: {
      ...validBody,
      tasks: [
        validBody.tasks[0],
        { session_id: second.session_id, expected_status: "blocked" },
      ],
    },
  });
  assert.equal(stale.status, 409);

  for (const [task, expected] of [[first, "todo"], [second, "active"]]) {
    const persisted = await (await operation("show", { session_id: task.session_id })).json();
    assert.equal(persisted.status, expected, `${task.session_id} must not be partially committed`);
    assert.equal(persisted.closed, null);
    assert.equal(
      persisted.rollouts.filter((rollout) => rollout.message.startsWith("status:")).length,
      0,
    );
  }

  const updated = await browser(path, {
    origin: "https://agtask.local",
    method: "PATCH",
    body: validBody,
  });
  assert.equal(updated.status, 200);
  const result = await updated.json();
  assert.equal(result.changed, true);
  assert.deepEqual(
    result.tasks.map((task) => task.session_id),
    [first.session_id, second.session_id],
  );
  assert.ok(result.tasks.every((task) => task.status === "drop" && task.closed === task.updated));

  for (const [task, expected] of [[first, "todo"], [second, "active"]]) {
    const persisted = await (await operation("show", { session_id: task.session_id })).json();
    assert.equal(persisted.status, "drop");
    assert.equal(
      persisted.rollouts.filter((rollout) => rollout.message === `status:${expected}->drop`).length,
      1,
    );
  }
});

test("dashboard status writes reject duplicate JSON keys without changing task state", async () => {
  const task = fixtureTask(
    "browser-duplicate-json-session",
    "a10bf864-c377-450f-8818-437dfb644a05",
  );
  assert.equal((await operation("register", task)).status, 200);

  const single = await browser(`/api/tasks/~${task.session_id}/status`, {
    origin: "https://agtask.local",
    method: "PATCH",
    rawBody: '{"expected_status":"active","status":"done","status":"drop"}',
  });
  assert.equal(single.status, 400, "duplicate top-level JSON keys must be rejected");

  const bulk = await browser("/api/tasks/status", {
    origin: "https://agtask.local",
    method: "PATCH",
    rawBody:
      '{"tasks":[{"session_id":"browser-duplicate-json-session",' +
      '"expected_status":"blocked","expected_status":"active"}],"status":"done"}',
  });
  assert.equal(bulk.status, 400, "duplicate keys nested inside bulk tasks must be rejected");

  const persisted = await (await operation("show", { session_id: task.session_id })).json();
  assert.equal(persisted.status, "active");
  assert.equal(persisted.closed, null);
  assert.equal(
    persisted.rollouts.filter((rollout) => rollout.message.startsWith("status:")).length,
    0,
  );
});

test("browser dashboard returns every matching task when D1 contains more than 200 rows", async () => {
  await setup;
  const d1 = await service.getD1Database("DB");
  const count = 205;
  const statements = Array.from({ length: count }, (_, index) => {
    const suffix = String(index).padStart(12, "0");
    const minute = String(Math.floor(index / 60)).padStart(2, "0");
    const second = String(index % 60).padStart(2, "0");
    const timestamp = `2026-08-10T12:${minute}:${second}.000Z`;

    return d1
      .prepare(
        "INSERT INTO agtask_threads " +
          "(id, session_id, parent_session_id, kind, project, title, description, " +
          "created, updated, closed, status) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, NULL, ?)",
      )
      .bind(
        `b10bf864-c377-450f-8818-${suffix}`,
        `browser-scale-${suffix}`,
        "main",
        "sites-scale",
        `Hosted scale task ${suffix}`,
        "Dashboard scale regression fixture.",
        timestamp,
        timestamp,
        "active",
      );
  });

  for (let index = 0; index < statements.length; index += 50) {
    await d1.batch(statements.slice(index, index + 50));
  }

  const response = await browser("/api/dashboard?project=sites-scale");
  assert.equal(response.status, 200);
  const snapshot = await response.json();
  const active = snapshot.groups.find((group) => group.status === "active");

  assert.equal(snapshot.visible_count, count);
  assert.equal(active.count, count);
  assert.equal(active.threads.length, count);
  assert.equal(
    snapshot.facets.projects.find((facet) => facet.value === "sites-scale").count,
    count,
  );
  assert.ok(active.threads.some((thread) => thread.session_id === "browser-scale-000000000000"));
  assert.ok(active.threads.some((thread) => thread.session_id === "browser-scale-000000000204"));
});

test("the existing probe still requires its original separate secret", async () => {
  const forbidden = await service.dispatchFetch("https://agtask.local/api/probe", {
    method: "POST",
    headers: {
      authorization: `Bearer ${taskSecret}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ message: "task token must not access probe" }),
  });
  assert.equal(forbidden.status, 401);

  const response = await service.dispatchFetch("https://agtask.local/api/probe", {
    method: "POST",
    headers: {
      authorization: `Bearer ${probeSecret}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ message: "existing probe remains available" }),
  });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).probe.message, "existing probe remains available");
});
