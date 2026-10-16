import { env } from "cloudflare:workers";
import {
  executeTaskOperation,
  TASK_STATUSES,
  TaskOperationError,
  type TaskRow,
} from "@/db/agtask";

type TaskStatus = (typeof TASK_STATUSES)[number];

export interface DashboardStatusUpdate {
  session_id: string;
  expected_status: TaskStatus;
}

type DashboardRow = Pick<
  TaskRow,
  | "id"
  | "session_id"
  | "parent_session_id"
  | "project"
  | "title"
  | "created"
  | "updated"
  | "closed"
  | "status"
>;

const DASHBOARD_COLUMNS =
  "id,session_id,parent_session_id,project,title,created,updated,closed,status";

function database() {
  if (!env.DB) {
    throw new TaskOperationError("Task storage is unavailable.", 503);
  }

  return env.DB;
}

function todayLocalDate(timestamp: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(timestamp));
}

export async function dashboardSnapshot(
  state: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const selectedView = state.view_id ?? null;

  if (selectedView !== null && selectedView !== "today") {
    throw new TaskOperationError(`unknown saved view: ${selectedView}`, 400);
  }

  const field = state.sort_field as "created" | "updated" | "closed";
  const direction = state.direction as "asc" | "desc";
  const projects = state.projects as string[];
  const parentSessionIds = state.parent_session_ids as string[];
  const statuses = state.statuses as TaskStatus[];
  const includeRoot = state.include_root as boolean;
  const search = state.search as string;
  const rows = (
    await database()
      .prepare(`SELECT ${DASHBOARD_COLUMNS} FROM agtask_threads`)
      .all<DashboardRow>()
  ).results.map((row) => ({ ...row, files: [] as [] }));
  const projectCounts = new Map<string, number>();
  const parentCounts = new Map<string | null, number>();
  const statusCounts = new Map<TaskStatus, number>();

  for (const row of rows) {
    projectCounts.set(row.project, (projectCounts.get(row.project) ?? 0) + 1);
    parentCounts.set(
      row.parent_session_id,
      (parentCounts.get(row.parent_session_id) ?? 0) + 1,
    );
    statusCounts.set(row.status, (statusCounts.get(row.status) ?? 0) + 1);
  }

  const viewTimestamp = new Date().toISOString();
  const today = selectedView === "today" ? todayLocalDate(viewTimestamp) : null;
  const needle = search.toLocaleLowerCase();
  const filtered = rows.filter((row) => {
    const parentMatches =
      (parentSessionIds.length === 0 && !includeRoot) ||
      (row.parent_session_id !== null &&
        parentSessionIds.includes(row.parent_session_id)) ||
      (includeRoot && row.parent_session_id === null);

    return (
      (projects.length === 0 || projects.includes(row.project)) &&
      parentMatches &&
      (statuses.length === 0 || statuses.includes(row.status)) &&
      (today === null ||
        (!["done", "drop"].includes(row.status) &&
          todayLocalDate(row.created) === today)) &&
      (!needle ||
        [row.title, row.id, row.session_id, row.parent_session_id ?? ""].some(
          (value) => value.toLocaleLowerCase().includes(needle),
        ))
    );
  });

  function compare(left: DashboardRow, right: DashboardRow): number {
    const leftValue = left[field];
    const rightValue = right[field];

    if (leftValue === null && rightValue !== null) return 1;
    if (leftValue !== null && rightValue === null) return -1;

    const compared = String(leftValue ?? "").localeCompare(
      String(rightValue ?? ""),
    );

    return (
      (direction === "asc" ? compared : -compared) ||
      right.updated.localeCompare(left.updated) ||
      right.created.localeCompare(left.created) ||
      left.id.localeCompare(right.id)
    );
  }

  const groupStatuses =
    statuses.length > 0
      ? statuses
      : TASK_STATUSES.filter(
          (status) => today === null || !["done", "drop"].includes(status),
        );
  const groups = groupStatuses.map((status) => {
    const threads = filtered.filter((row) => row.status === status).sort(compare);

    return { status, count: threads.length, threads };
  });

  const snapshot: Record<string, unknown> = {
    filters: {
      projects,
      parent_session_ids: parentSessionIds,
      include_root: includeRoot,
      statuses,
    },
    search,
    selected_view: selectedView,
    sort: { field, direction },
    total_count: rows.length,
    visible_count: filtered.length,
    facets: {
      projects: [...projectCounts]
        .sort(([left], [right]) =>
          left.localeCompare(right, undefined, { sensitivity: "base" }),
        )
        .map(([value, count]) => ({ value, count })),
      parents: [...parentCounts]
        .sort(([left], [right]) => {
          if (left === null && right !== null) return -1;
          if (left !== null && right === null) return 1;

          return (left ?? "").localeCompare(right ?? "", undefined, {
            sensitivity: "base",
          });
        })
        .map(([value, count]) => ({ value, count })),
      statuses: TASK_STATUSES.map((status) => ({
        value: status,
        count: statusCounts.get(status) ?? 0,
      })),
    },
    groups,
  };

  snapshot.views = [
    {
      id: "today",
      name: "Today",
      filters: { created: "today", exclude_statuses: ["done", "drop"] },
      created: viewTimestamp,
      updated: viewTimestamp,
    },
  ];
  return snapshot;
}

export async function dashboardTaskDetail(sessionId: string) {
  const detail = (await executeTaskOperation("show", {
    session_id: sessionId,
  })) as TaskRow & {
    rollouts: Array<{ created: string; role: string; message: string }>;
    files: [];
  };

  return {
    id: detail.id,
    session_id: detail.session_id,
    parent_session_id: detail.parent_session_id,
    title: detail.title,
    description: detail.description,
    created: detail.created,
    updated: detail.updated,
    rollouts: detail.rollouts.map(({ created, role, message }) => ({
      created,
      role,
      message,
    })),
    files: [],
  };
}

function conflict(expected: string, current: string): TaskOperationError {
  return new TaskOperationError(
    `task status changed from ${expected} to ${current}; refresh and try again`,
    409,
  );
}

export async function updateDashboardTaskStatuses(
  updates: DashboardStatusUpdate[],
  target: TaskStatus,
): Promise<{ changed: boolean; tasks: DashboardRow[] }> {
  const d1 = database();
  const reads = await d1.batch(
    updates.map(({ session_id }) =>
      d1
        .prepare(`SELECT ${DASHBOARD_COLUMNS} FROM agtask_threads WHERE session_id = ?`)
        .bind(session_id),
    ),
  );
  const tasks = updates.map(({ expected_status }, index) => {
    const task = reads[index].results[0] as DashboardRow | undefined;

    if (!task) {
      throw new TaskOperationError("task not found", 404);
    }

    if (task.status !== expected_status) {
      throw conflict(expected_status, task.status);
    }

    if (task.status !== target && ["done", "drop"].includes(task.status)) {
      const label = task.status === "drop" ? "dropped" : task.status;
      throw new TaskOperationError(
        `${label} threads must be reopened explicitly`,
        409,
      );
    }

    if (task.status === "merging") {
      throw new TaskOperationError(
        "merging threads must be closed or released explicitly",
        409,
      );
    }

    return task;
  });
  const timestamp = new Date().toISOString();
  const statements = tasks.flatMap((task) => {
    if (task.status === target) {
      return [
        d1
          .prepare(
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM agtask_threads " +
              "WHERE id = ? AND status = ?) THEN 1 " +
              "ELSE json_extract('invalid', '$') END AS guarded",
          )
          .bind(task.id, task.status),
      ];
    }

    const closed = target === "done" || target === "drop" ? timestamp : null;

    return [
      d1
        .prepare(
          "UPDATE agtask_threads SET status = ?,updated = ?,closed = ? " +
            "WHERE id = ? AND status = ?",
        )
        .bind(target, timestamp, closed, task.id, task.status),
      // D1 batch is transactional. Deliberately abort a stale CAS so every
      // earlier update and lifecycle event rolls back together.
      d1.prepare(
        "SELECT CASE WHEN changes() = 1 THEN 1 " +
          "ELSE json_extract('invalid', '$') END AS applied",
      ),
      d1
        .prepare(
          "INSERT INTO agtask_rollouts " +
            "(created,thread_id,turn_id,role,message) VALUES (?, ?, ?, 'meta', ?)",
        )
        .bind(
          timestamp,
          task.id,
          crypto.randomUUID(),
          `status:${task.status}->${target}`,
        ),
    ];
  });

  try {
    await d1.batch(statements);
  } catch {
    for (const { session_id, expected_status } of updates) {
      const current = await d1
        .prepare("SELECT status FROM agtask_threads WHERE session_id = ?")
        .bind(session_id)
        .first<{ status: string }>();

      if (!current) {
        throw new TaskOperationError("task not found", 404);
      }

      if (current.status !== expected_status) {
        throw conflict(expected_status, current.status);
      }
    }

    throw new TaskOperationError("Task storage is unavailable.", 503);
  }

  return {
    changed: tasks.some((task) => task.status !== target),
    tasks: tasks.map((task) =>
      task.status === target
        ? task
        : {
            ...task,
            status: target,
            updated: timestamp,
            closed: ["done", "drop"].includes(target) ? timestamp : null,
          },
    ),
  };
}
