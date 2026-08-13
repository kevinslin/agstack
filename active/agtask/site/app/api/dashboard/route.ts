import { TASK_STATUSES, TaskOperationError } from "@/db/agtask";
import { dashboardSnapshot } from "@/db/dashboard";
import {
  dashboardError,
  dashboardResponse,
  requireDashboardIdentity,
} from "@/app/api/_lib/dashboard";

const ALLOWED_KEYS = new Set([
  "project",
  "parent_session_id",
  "root_parent",
  "status",
  "sort",
  "direction",
  "search",
  "view",
]);
const SINGLE_KEYS = new Set([
  "root_parent",
  "sort",
  "direction",
  "search",
  "view",
]);

function stateFromUrl(request: Request): Record<string, unknown> {
  const url = new URL(request.url);
  const values = new Map<string, string[]>();
  let count = 0;

  for (const [key, value] of url.searchParams) {
    if (++count > 100) {
      throw new TaskOperationError("invalid dashboard query string", 400);
    }

    if (!ALLOWED_KEYS.has(key)) {
      throw new TaskOperationError(`unknown query parameter: ${key}`, 400);
    }

    const existing = values.get(key) ?? [];

    if (SINGLE_KEYS.has(key) && existing.length > 0) {
      throw new TaskOperationError(`duplicate query parameter: ${key}`, 400);
    }

    if (["project", "parent_session_id", "status", "view"].includes(key) && !value) {
      throw new TaskOperationError(`${key} must not be empty`, 400);
    }

    existing.push(value);
    values.set(key, existing);
  }

  const root = values.get("root_parent")?.[0];
  if (root !== undefined && root !== "1") {
    throw new TaskOperationError("root_parent must equal 1", 400);
  }

  const sort = values.get("sort")?.[0] ?? "updated";
  if (!["created", "updated", "closed"].includes(sort)) {
    throw new TaskOperationError(`invalid dashboard sort field: ${sort}`, 400);
  }

  const direction = values.get("direction")?.[0] ?? "desc";
  if (direction !== "asc" && direction !== "desc") {
    throw new TaskOperationError(`invalid dashboard direction: ${direction}`, 400);
  }

  const statuses = values.get("status") ?? [];
  for (const status of statuses) {
    if (!TASK_STATUSES.includes(status as (typeof TASK_STATUSES)[number])) {
      throw new TaskOperationError(`invalid dashboard status: ${status}`, 400);
    }
  }

  const normalize = (entries: string[]) =>
    [...new Set(entries)].sort((left, right) =>
      left.localeCompare(right, undefined, { sensitivity: "base" }),
    );

  return {
    projects: normalize(values.get("project") ?? []),
    parent_session_ids: normalize(values.get("parent_session_id") ?? []),
    include_root: root === "1",
    statuses: TASK_STATUSES.filter((status) => statuses.includes(status)),
    sort_field: sort,
    direction,
    search: values.get("search")?.[0] ?? "",
    view_id: values.get("view")?.[0] ?? null,
  };
}

export async function GET(request: Request): Promise<Response> {
  const denied = requireDashboardIdentity(request);
  if (denied) return denied;

  try {
    return dashboardResponse(await dashboardSnapshot(stateFromUrl(request)));
  } catch (error) {
    return dashboardError(error);
  }
}
