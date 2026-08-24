import { env } from "cloudflare:workers";

export const TASK_STATUSES = [
  "todo",
  "active",
  "blocked",
  "merging",
  "done",
  "drop",
] as const;

type TaskStatus = (typeof TASK_STATUSES)[number];
type TaskRole = "user" | "assistant" | "meta";
type Payload = Record<string, unknown>;

export interface TaskRow {
  id: string;
  session_id: string;
  parent_session_id: string | null;
  kind: "main" | "child";
  project: string;
  title: string;
  description: string;
  created: string;
  updated: string;
  closed: string | null;
  status: TaskStatus;
}

interface RolloutRow {
  id: number;
  created: string;
  thread_id: string;
  turn_id: string;
  role: TaskRole;
  message: string;
}

export interface TaskDetail extends TaskRow {
  rollouts: RolloutRow[];
  files: [];
}

type AuditTask = Pick<
  TaskRow,
  "id" | "session_id" | "parent_session_id" | "project" | "title" | "updated" | "status"
>;
type AuditObservation = {
  session_id: string;
  state: "archived" | "not_archived" | "missing" | "error";
  detail?: string;
};

export class TaskOperationError extends Error {
  constructor(
    message: string,
    readonly status: 400 | 404 | 409 | 503,
  ) {
    super(message);
  }
}

function database() {
  if (!env.DB) {
    throw new TaskOperationError("Task storage is unavailable.", 503);
  }

  return env.DB;
}

function requiredString(
  payload: Payload,
  key: string,
  maxLength = 256,
): string {
  const value = payload[key];

  if (
    typeof value !== "string" ||
    value.trim().length === 0 ||
    value.length > maxLength
  ) {
    throw new TaskOperationError(
      `${key} must contain 1 to ${maxLength} characters.`,
      400,
    );
  }

  if (value !== value.trim()) {
    throw new TaskOperationError(`${key} must not contain surrounding whitespace.`, 400);
  }

  return value;
}

function requiredSummary(payload: Payload, key: string): string {
  const value = requiredString(payload, key, 240);

  if (/[\r\n]/.test(value)) {
    throw new TaskOperationError(`${key} must be a normalized one-line summary.`, 400);
  }

  return value;
}

function readStatus(value: unknown): TaskStatus {
  if (
    typeof value !== "string" ||
    !TASK_STATUSES.includes(value as TaskStatus)
  ) {
    throw new TaskOperationError("The task status is invalid.", 400);
  }

  return value as TaskStatus;
}

function readLimit(value: unknown, fallback: number): number {
  if (value === undefined || value === null) return fallback;

  if (!Number.isSafeInteger(value) || Number(value) < 1 || Number(value) > 200) {
    throw new TaskOperationError("limit must be an integer between 1 and 200.", 400);
  }

  return Number(value);
}

function selectedIdentity(payload: Payload): { field: "id" | "session_id"; value: string } {
  const hasId = payload.id !== undefined && payload.id !== null;
  const hasSessionId =
    payload.session_id !== undefined && payload.session_id !== null;

  if (hasId === hasSessionId) {
    throw new TaskOperationError("Provide exactly one task id or session_id.", 400);
  }

  const field = hasId ? "id" : "session_id";
  return { field, value: requiredString(payload, field) };
}

async function findTask(payload: Payload): Promise<TaskRow> {
  const { field, value } = selectedIdentity(payload);
  const row = await database()
    .prepare(`SELECT * FROM agtask_threads WHERE ${field} = ?`)
    .bind(value)
    .first<TaskRow>();

  if (!row) {
    throw new TaskOperationError("The requested task is not tracked.", 404);
  }

  return row;
}

export async function taskDetail(id: string): Promise<TaskDetail> {
  const d1 = database();
  const [taskResult, rolloutResult] = await d1.batch([
    d1.prepare("SELECT * FROM agtask_threads WHERE id = ?").bind(id),
    d1
      .prepare(
        "SELECT id, created, thread_id, turn_id, role, message " +
          "FROM agtask_rollouts WHERE thread_id = ? ORDER BY created DESC, id DESC",
      )
      .bind(id),
  ]);
  const task = taskResult.results[0] as TaskRow | undefined;

  if (!task) {
    throw new TaskOperationError("The requested task is not tracked.", 404);
  }

  return {
    ...task,
    rollouts: rolloutResult.results as RolloutRow[],
    files: [],
  };
}

export async function listTasks(payload: Payload = {}): Promise<TaskRow[]> {
  const conditions: string[] = [];
  const values: (string | number)[] = [];

  if (payload.status !== undefined && payload.status !== null) {
    conditions.push("status = ?");
    values.push(readStatus(payload.status));
  }

  if (payload.project !== undefined && payload.project !== null) {
    conditions.push("project = ?");
    values.push(requiredString(payload, "project"));
  }

  if (payload.filters !== undefined && payload.filters !== null) {
    if (!Array.isArray(payload.filters)) {
      throw new TaskOperationError("filters must be an array.", 400);
    }

    for (const filter of payload.filters) {
      if (
        typeof filter !== "object" ||
        filter === null ||
        !("field" in filter) ||
        !("start" in filter) ||
        !("end" in filter) ||
        (filter.field !== "created" && filter.field !== "updated") ||
        typeof filter.start !== "string" ||
        typeof filter.end !== "string"
      ) {
        throw new TaskOperationError("filters must contain valid timestamp ranges.", 400);
      }

      conditions.push(`${filter.field} >= ?`, `${filter.field} < ?`);
      values.push(filter.start, filter.end);
    }
  }

  const where = conditions.length ? ` WHERE ${conditions.join(" AND ")}` : "";
  const limit = readLimit(payload.limit, 50);
  const result = await database()
    .prepare(
      `SELECT * FROM agtask_threads${where} ` +
        "ORDER BY updated DESC, created DESC, id ASC LIMIT ?",
    )
    .bind(...values, limit)
    .all<TaskRow>();

  return result.results;
}

function auditObservations(payload: Payload): Map<string, AuditObservation> | null {
  if (payload.observations === undefined) return null;

  const document = payload.observations;

  if (
    !document ||
    typeof document !== "object" ||
    Array.isArray(document) ||
    Object.keys(document).length !== 2 ||
    !("schema_version" in document) ||
    document.schema_version !== 1 ||
    !("sessions" in document) ||
    !Array.isArray(document.sessions)
  ) {
    throw new TaskOperationError("Audit observations must use the version-1 schema.", 400);
  }

  const observations = new Map<string, AuditObservation>();

  for (const value of document.sessions) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new TaskOperationError("Each audit observation must be an object.", 400);
    }

    const observation = value as Payload;
    const keys = Object.keys(observation);

    if (
      !keys.includes("session_id") ||
      !keys.includes("state") ||
      keys.some((key) => !["session_id", "state", "detail"].includes(key))
    ) {
      throw new TaskOperationError("The audit observation fields are invalid.", 400);
    }

    const sessionId = requiredString(observation, "session_id");
    const state = observation.state;

    if (
      state !== "archived" &&
      state !== "not_archived" &&
      state !== "missing" &&
      state !== "error"
    ) {
      throw new TaskOperationError("The archive lookup state is invalid.", 400);
    }

    if (
      (state === "error" &&
        (typeof observation.detail !== "string" || !observation.detail.trim())) ||
      (state !== "error" && observation.detail !== undefined)
    ) {
      throw new TaskOperationError("Only failed archive lookups require error detail.", 400);
    }

    if (observations.has(sessionId)) {
      throw new TaskOperationError("Duplicate archive observations are not allowed.", 400);
    }

    observations.set(sessionId, {
      session_id: sessionId,
      state,
      ...(typeof observation.detail === "string" ? { detail: observation.detail } : {}),
    });
  }

  return observations;
}

async function auditTasks(payload: Payload): Promise<Record<string, unknown>> {
  if (Object.keys(payload).some((key) => !["observations", "apply"].includes(key))) {
    throw new TaskOperationError("The audit request contains unsupported fields.", 400);
  }

  const observations = auditObservations(payload);
  const apply = payload.apply;

  if (
    apply !== undefined &&
    (observations === null || typeof apply !== "string" || !/^[0-9a-f]{64}$/.test(apply))
  ) {
    throw new TaskOperationError("Audit apply requires observations and a valid plan token.", 400);
  }

  const d1 = database();
  const activeTasks: AuditTask[] = (
    await d1
      .prepare(
        "SELECT id, session_id, parent_session_id, project, title, updated, status " +
          "FROM agtask_threads WHERE status IN ('todo', 'active', 'blocked') " +
          "ORDER BY session_id, id",
      )
      .all<AuditTask>()
  ).results;
  const affectedTasks: AuditTask[] = [];
  const unresolved: Record<string, string>[] = [];
  const activeSessionIds = new Set(activeTasks.map((task) => task.session_id));
  const report: Record<string, unknown> = {
    phase: observations === null ? "lookup_required" : "complete",
    applied: false,
    active_tasks: activeTasks,
    lookup_requests: activeTasks.map((task) => ({ session_id: task.session_id })),
    affected_tasks: affectedTasks,
    unresolved,
    ignored_observations:
      observations === null
        ? []
        : [...observations.keys()].filter((sessionId) => !activeSessionIds.has(sessionId)).sort(),
    plan_token: null,
  };

  if (observations === null) return report;

  for (const task of activeTasks) {
    const observation = observations.get(task.session_id);

    if (!observation) {
      unresolved.push({
        id: task.id,
        session_id: task.session_id,
        lookup_state: "unobserved",
      });
    } else if (observation.state === "archived") {
      affectedTasks.push(task);
    } else if (observation.state === "missing" || observation.state === "error") {
      unresolved.push({
        id: task.id,
        session_id: task.session_id,
        lookup_state: observation.state,
        ...(observation.detail === undefined ? {} : { detail: observation.detail }),
      });
    }
  }

  unresolved.sort((left, right) =>
    left.session_id.localeCompare(right.session_id) || left.id.localeCompare(right.id),
  );

  if (!affectedTasks.length) return report;

  const tokenPayload = {
    tasks: activeTasks.map((task) => ({
      id: task.id,
      lookup_state: observations.get(task.session_id)?.state ?? "unobserved",
      session_id: task.session_id,
      status: task.status,
      updated: task.updated,
    })),
    version: 2,
  };
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(JSON.stringify(tokenPayload)),
  );
  const planToken = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");

  report.phase = "confirmation_required";
  report.plan_token = planToken;

  if (apply === undefined) return report;

  if (apply !== planToken) {
    throw new TaskOperationError(
      "The audit plan changed; review the affected tasks and obtain confirmation again.",
      409,
    );
  }

  const timestamp = new Date().toISOString();
  const statements = [
    d1
      .prepare(
        "SELECT CASE WHEN (SELECT COUNT(*) FROM agtask_threads " +
          "WHERE status IN ('todo', 'active', 'blocked')) = ? THEN 1 " +
          "ELSE json_extract('invalid', '$') END AS verified",
      )
      .bind(activeTasks.length),
  ];

  for (const task of activeTasks) {
    statements.push(
      d1
        .prepare(
          "SELECT CASE WHEN EXISTS(SELECT 1 FROM agtask_threads " +
            "WHERE id = ? AND session_id = ? AND status = ? AND updated = ?) " +
            "THEN 1 ELSE json_extract('invalid', '$') END AS verified",
        )
        .bind(task.id, task.session_id, task.status, task.updated),
    );
  }

  for (const task of affectedTasks) {
    statements.push(
      d1
        .prepare(
          "UPDATE agtask_threads SET status = 'done', updated = ?, closed = ? " +
            "WHERE id = ? AND session_id = ? AND status = ? AND updated = ?",
        )
        .bind(timestamp, timestamp, task.id, task.session_id, task.status, task.updated),
      d1.prepare(
        "SELECT CASE WHEN changes() = 1 THEN 1 " +
          "ELSE json_extract('invalid', '$') END AS applied",
      ),
      d1
        .prepare(
          "INSERT INTO agtask_rollouts (created, thread_id, turn_id, role, message) " +
            "VALUES (?, ?, ?, 'meta', ?)",
        )
        .bind(timestamp, task.id, crypto.randomUUID(), `status:${task.status}->done`),
      d1
        .prepare(
          "INSERT INTO agtask_rollouts (created, thread_id, turn_id, role, message) " +
            "VALUES (?, ?, ?, 'meta', 'archival:codex-thread-archived')",
        )
        .bind(timestamp, task.id, crypto.randomUUID()),
    );
  }

  try {
    await d1.batch(statements);
  } catch {
    throw new TaskOperationError(
      "The audit plan changed; review the affected tasks and obtain confirmation again.",
      409,
    );
  }

  report.phase = "complete";
  report.applied = true;
  return report;
}

async function registerTask(payload: Payload): Promise<TaskDetail & { task_created: boolean }> {
  const id = requiredString(payload, "id", 128);

  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id)) {
    throw new TaskOperationError("id must be a canonical UUIDv4.", 400);
  }

  const sessionId = requiredString(payload, "session_id");
  const project = requiredString(payload, "project");
  const title = requiredString(payload, "title", 512);
  const kind = payload.kind;
  const status = readStatus(payload.status ?? "active");
  const parentSessionId =
    payload.parent_session_id === undefined || payload.parent_session_id === null
      ? null
      : requiredString(payload, "parent_session_id");

  if (kind !== "main" && kind !== "child") {
    throw new TaskOperationError("kind must be main or child.", 400);
  }

  if ((kind === "main" && parentSessionId !== null) ||
      (kind === "child" && parentSessionId === null)) {
    throw new TaskOperationError(
      "Main tasks cannot have a parent; child tasks require a parent.",
      400,
    );
  }

  if (parentSessionId === sessionId) {
    throw new TaskOperationError("A task cannot name itself as its parent.", 400);
  }

  if (status !== "todo" && status !== "active") {
    throw new TaskOperationError("New tasks must be todo or active.", 400);
  }

  const initialPrompt =
    payload.initial_prompt === undefined || payload.initial_prompt === null
      ? null
      : requiredSummary(payload, "initial_prompt");
  const assertedDescription =
    payload.description === undefined || payload.description === null
      ? null
      : requiredSummary(payload, "description");

  if (
    initialPrompt !== null &&
    assertedDescription !== null &&
    initialPrompt !== assertedDescription
  ) {
    throw new TaskOperationError("description conflicts with initial_prompt.", 400);
  }

  const description = initialPrompt ?? assertedDescription;

  if (description === null) {
    throw new TaskOperationError("A normalized task description is required.", 400);
  }

  const d1 = database();
  const existing = await d1
    .prepare("SELECT * FROM agtask_threads WHERE id = ? OR session_id = ?")
    .bind(id, sessionId)
    .all<TaskRow>();
  const matchesRegistration = (row: TaskRow | undefined): row is TaskRow =>
    row !== undefined &&
    row.id === id &&
    row.session_id === sessionId &&
    row.parent_session_id === parentSessionId &&
    row.kind === kind &&
    row.project === project &&
    row.title === title &&
    row.description === description;

  if (existing.results.length > 0) {
    if (existing.results.length !== 1 || !matchesRegistration(existing.results[0])) {
      throw new TaskOperationError(
        "Task registration conflicts with an existing task or session.",
        409,
      );
    }

    return { ...(await taskDetail(id)), task_created: false };
  }

  const timestamp = new Date().toISOString();

  try {
    await d1.batch([
      d1
        .prepare(
          "INSERT INTO agtask_threads " +
            "(id, session_id, parent_session_id, kind, project, title, description, " +
            "created, updated, closed, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
        )
        .bind(
          id,
          sessionId,
          parentSessionId,
          kind,
          project,
          title,
          description,
          timestamp,
          timestamp,
          status,
        ),
      d1
        .prepare(
          "INSERT INTO agtask_rollouts " +
            "(created, thread_id, turn_id, role, message) " +
            "VALUES (?, ?, 'thread.created', 'meta', 'thread.created')",
        )
        .bind(timestamp, id),
    ]);
  } catch (error) {
    const cause = error instanceof Error && error.cause instanceof Error
      ? error.cause.message
      : "";

    if (
      error instanceof Error &&
      /unique|constraint/i.test(`${error.message} ${cause}`)
    ) {
      const winner = await d1
        .prepare("SELECT * FROM agtask_threads WHERE id = ? OR session_id = ?")
        .bind(id, sessionId)
        .all<TaskRow>();

      if (winner.results.length === 1 && matchesRegistration(winner.results[0])) {
        return { ...(await taskDetail(id)), task_created: false };
      }

      throw new TaskOperationError("Task registration conflicts with existing data.", 409);
    }

    throw error;
  }

  return { ...(await taskDetail(id)), task_created: true };
}

async function addTask(payload: Payload): Promise<TaskDetail & { task_created: boolean }> {
  const sessionId = requiredString(payload, "session_id");
  const existing = await database()
    .prepare("SELECT id, kind FROM agtask_threads WHERE session_id = ?")
    .bind(sessionId)
    .first<Pick<TaskRow, "id" | "kind">>();

  if (existing && existing.kind !== "main") {
    throw new TaskOperationError("An existing child task cannot be added as a main task.", 409);
  }

  return registerTask({
    ...payload,
    id: existing?.id ?? crypto.randomUUID(),
    session_id: sessionId,
    parent_session_id: null,
    kind: "main",
    status: "active",
  });
}

async function appendTaskRollout(
  payload: Payload,
  recordedTurn: boolean,
): Promise<TaskDetail> {
  const task = await findTask(payload);
  const turnId = requiredString(payload, "turn_id");
  const role = payload.role;

  if (
    role !== "user" &&
    role !== "assistant" &&
    !(role === "meta" && !recordedTurn)
  ) {
    throw new TaskOperationError("The rollout role is invalid.", 400);
  }

  const summaryKey =
    typeof payload.summary === "string"
      ? "summary"
      : typeof payload.message === "string"
        ? "message"
        : "content";
  const message = requiredSummary(payload, summaryKey);
  const d1 = database();
  const existing = await d1
    .prepare(
      "SELECT message FROM agtask_rollouts " +
        "WHERE thread_id = ? AND role = ? AND turn_id = ?",
    )
    .bind(task.id, role, turnId)
    .first<{ message: string }>();

  if (existing) {
    if (existing.message !== message) {
      throw new TaskOperationError("This rollout event conflicts with an existing event.", 409);
    }

    return taskDetail(task.id);
  }

  const timestamp = new Date().toISOString();
  const targetStatus =
    !recordedTurn || ["done", "drop", "merging"].includes(task.status)
      ? task.status
      : role === "assistant" && message.startsWith("Blocked:")
        ? "blocked"
        : "active";
  const statements = [
    d1
      .prepare(
        "INSERT INTO agtask_rollouts (created, thread_id, turn_id, role, message) " +
          "VALUES (?, ?, ?, ?, ?) " +
          "ON CONFLICT(thread_id, role, turn_id) DO NOTHING",
      )
      .bind(timestamp, task.id, turnId, role, message),
    d1
      .prepare(
        "UPDATE agtask_threads SET updated = ?, status = ? " +
          "WHERE id = ? AND status = ? AND changes() = 1 AND EXISTS " +
          "(SELECT 1 FROM agtask_rollouts WHERE thread_id = ? " +
          "AND role = ? AND turn_id = ? AND message = ?)",
      )
      .bind(
        timestamp,
        targetStatus,
        task.id,
        task.status,
        task.id,
        role,
        turnId,
        message,
      ),
    // A stale compare-and-swap must roll back the inserted event too. D1 batch
    // is transactional; forcing a SQLite JSON error aborts every prior statement.
    d1.prepare(
      "SELECT CASE WHEN changes() = 1 THEN 1 " +
        "ELSE json_extract('invalid', '$') END AS applied",
    ),
  ];

  if (targetStatus !== task.status) {
    statements.push(
      d1
        .prepare(
          "INSERT INTO agtask_rollouts " +
            "(created, thread_id, turn_id, role, message) " +
            "SELECT ?, ?, ?, 'meta', ? WHERE changes() = 1",
        )
        .bind(
          timestamp,
          task.id,
          crypto.randomUUID(),
          `status:${task.status}->${targetStatus}`,
        ),
    );
  }

  try {
    await d1.batch(statements);
  } catch {
    const winner = await d1
      .prepare(
        "SELECT message FROM agtask_rollouts " +
          "WHERE thread_id = ? AND role = ? AND turn_id = ?",
      )
      .bind(task.id, role, turnId)
      .first<{ message: string }>();

    if (winner?.message === message) {
      return taskDetail(task.id);
    }

    throw new TaskOperationError(
      winner
        ? "This rollout event conflicts with an existing event."
        : "The task status changed before this rollout was recorded.",
      409,
    );
  }

  const stored = await d1
    .prepare(
      "SELECT message FROM agtask_rollouts " +
        "WHERE thread_id = ? AND role = ? AND turn_id = ?",
    )
    .bind(task.id, role, turnId)
    .first<{ message: string }>();

  if (stored?.message !== message) {
    throw new TaskOperationError("This rollout event conflicts with an existing event.", 409);
  }

  return taskDetail(task.id);
}

async function transitionTask(
  payload: Payload,
  reopening: boolean,
): Promise<TaskDetail> {
  const task = await findTask(payload);
  const target = reopening ? "active" : readStatus(payload.status);

  if (!reopening && !["todo", "active", "blocked", "drop"].includes(target)) {
    throw new TaskOperationError("The requested manual task status is invalid.", 400);
  }

  if (task.status === target || (reopening && !["done", "drop"].includes(task.status))) {
    return taskDetail(task.id);
  }

  if (!reopening && ["done", "drop"].includes(task.status)) {
    throw new TaskOperationError("Terminal tasks must be reopened explicitly.", 409);
  }

  if (task.status === "merging") {
    throw new TaskOperationError("Merging tasks must be released explicitly.", 409);
  }

  const timestamp = new Date().toISOString();
  const closed = target === "drop" || target === "done" ? timestamp : null;
  const d1 = database();
  const results = await d1.batch([
    d1
      .prepare(
        "UPDATE agtask_threads SET status = ?, updated = ?, closed = ? " +
          "WHERE id = ? AND status = ?",
      )
      .bind(target, timestamp, closed, task.id, task.status),
    d1
      .prepare(
        "INSERT INTO agtask_rollouts " +
          "(created, thread_id, turn_id, role, message) " +
          "SELECT ?, ?, ?, 'meta', ? WHERE changes() = 1",
      )
      .bind(
        timestamp,
        task.id,
        crypto.randomUUID(),
        `status:${task.status}->${target}`,
      ),
  ]);

  if (results[0].meta.changes !== 1) {
    throw new TaskOperationError("The task status changed before this update.", 409);
  }

  return taskDetail(task.id);
}

async function searchTasks(payload: Payload): Promise<TaskRow[]> {
  const query = requiredString(payload, "query");
  const escaped = query.replace(/[\\%_]/g, "\\$&");
  const pattern = `%${escaped}%`;
  const result = await database()
    .prepare(
      "SELECT * FROM agtask_threads " +
        "WHERE title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\' " +
        "ORDER BY updated DESC, created DESC LIMIT ?",
    )
    .bind(pattern, pattern, readLimit(payload.limit, 20))
    .all<TaskRow>();

  return result.results;
}

function stringArray(value: unknown, label: string): string[] {
  if (value === undefined || value === null) return [];

  if (
    !Array.isArray(value) ||
    value.some((entry) => typeof entry !== "string" || !entry.trim())
  ) {
    throw new TaskOperationError(`${label} must be an array of nonempty strings.`, 400);
  }

  return [...new Set(value as string[])];
}

async function dashboardSnapshot(payload: Payload): Promise<Payload> {
  if (payload.view_id !== undefined && payload.view_id !== null) {
    throw new TaskOperationError("Saved dashboard views are not available.", 400);
  }

  const rows = await listTasks({ limit: 200 });
  const projects = stringArray(payload.projects ?? payload.project, "projects");
  const parentSessionIds = stringArray(
    payload.parent_session_ids ?? payload.parent_session_id,
    "parent_session_ids",
  );
  const statuses = stringArray(payload.statuses ?? payload.status, "statuses");

  statuses.forEach(readStatus);

  const includeRoot = Boolean(payload.include_root ?? payload.root_parent);
  const search = typeof payload.search === "string" ? payload.search : "";
  const field = typeof payload.sort_field === "string" ? payload.sort_field :
    typeof payload.sort === "string" ? payload.sort : "updated";
  const direction = payload.direction === "asc" ? "asc" : "desc";
  const sortFields = ["updated", "created", "title", "project", "status"];

  if (!sortFields.includes(field)) {
    throw new TaskOperationError("The dashboard sort field is invalid.", 400);
  }

  const projectCounts = new Map<string, number>();
  const parentCounts = new Map<string | null, number>();
  const statusCounts = new Map<string, number>();

  for (const row of rows) {
    projectCounts.set(row.project, (projectCounts.get(row.project) ?? 0) + 1);
    parentCounts.set(
      row.parent_session_id,
      (parentCounts.get(row.parent_session_id) ?? 0) + 1,
    );
    statusCounts.set(row.status, (statusCounts.get(row.status) ?? 0) + 1);
  }

  const needle = search.toLocaleLowerCase();
  const filtered = rows.filter((row) => {
    const parentMatches =
      (parentSessionIds.length === 0 && !includeRoot) ||
      (row.parent_session_id !== null && parentSessionIds.includes(row.parent_session_id)) ||
      (includeRoot && row.parent_session_id === null);

    return (
      (projects.length === 0 || projects.includes(row.project)) &&
      parentMatches &&
      (statuses.length === 0 || statuses.includes(row.status)) &&
      (!needle ||
        [row.title, row.id, row.session_id, row.parent_session_id ?? ""].some(
          (value) => value.toLocaleLowerCase().includes(needle),
        ))
    );
  });

  const compare = (left: TaskRow, right: TaskRow): number => {
    const leftValue = String(left[field as keyof TaskRow] ?? "");
    const rightValue = String(right[field as keyof TaskRow] ?? "");
    const result = leftValue.localeCompare(rightValue);

    return (direction === "asc" ? result : -result) || right.updated.localeCompare(left.updated);
  };

  return {
    filters: {
      projects,
      parent_session_ids: parentSessionIds,
      include_root: includeRoot,
      statuses,
    },
    search,
    selected_view: null,
    views: [],
    sort: { field, direction },
    total_count: rows.length,
    visible_count: filtered.length,
    facets: {
      projects: [...projectCounts]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([value, count]) => ({ value, count })),
      parents: [...parentCounts]
        .sort(([left], [right]) => (left ?? "").localeCompare(right ?? ""))
        .map(([value, count]) => ({ value, count })),
      statuses: TASK_STATUSES.map((status) => ({
        value: status,
        count: statusCounts.get(status) ?? 0,
      })),
    },
    groups: (statuses.length > 0 ? statuses : TASK_STATUSES).map((status) => {
      const threads = filtered
        .filter((row) => row.status === status)
        .sort(compare)
        .map((row) => ({ ...row, files: [] }));

      return { status, count: threads.length, threads };
    }),
  };
}

export async function executeTaskOperation(
  operation: string,
  payload: Payload,
): Promise<unknown> {
  switch (operation) {
    case "health":
      await database().prepare("SELECT 1 FROM agtask_threads LIMIT 1").all();
      return { status: "ok", backend: "sites", schema_version: 1 };
    case "register":
      return registerTask(payload);
    case "add":
      return addTask(payload);
    case "audit":
      return auditTasks(payload);
    case "show":
      return taskDetail((await findTask(payload)).id);
    case "list":
      return listTasks(payload);
    case "record-turn":
      return appendTaskRollout(payload, true);
    case "append-rollout":
      return appendTaskRollout(payload, false);
    case "status":
      return transitionTask(payload, false);
    case "reopen":
      return transitionTask(payload, true);
    case "search":
      return searchTasks(payload);
    case "dashboard":
      return dashboardSnapshot(payload);
    default:
      throw new TaskOperationError("The requested task operation is not supported.", 404);
  }
}
