import { TASK_STATUSES, TaskOperationError } from "@/db/agtask";
import {
  updateDashboardTaskStatuses,
  type DashboardStatusUpdate,
} from "@/db/dashboard";

type TaskStatus = (typeof TASK_STATUSES)[number];

const MUTATION_STATUSES = new Set<TaskStatus>([
  "todo",
  "active",
  "blocked",
  "done",
  "drop",
]);
const SECURITY_HEADERS = {
  "cache-control": "no-store",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
};

export function dashboardResponse(value: unknown, status = 200): Response {
  return Response.json(value, { status, headers: SECURITY_HEADERS });
}

export function dashboardError(error: unknown): Response {
  if (error instanceof TaskOperationError) {
    return dashboardResponse({ error: error.message }, error.status);
  }

  return dashboardResponse({ error: "Task storage is unavailable." }, 503);
}

export function requireDashboardIdentity(request: Request): Response | null {
  const userId = request.headers.get("oai-authenticated-user-id");

  if (!userId || !userId.trim()) {
    return dashboardResponse({ error: "Authentication is required." }, 401);
  }

  return null;
}

export function dashboardSessionId(session: string): string | null {
  if (!session.startsWith("~")) return null;

  const sessionId = session.slice(1);

  if (!sessionId || sessionId.length > 256 || sessionId.includes("/")) {
    return null;
  }

  return sessionId;
}

function validKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();

  return (
    actual.length === expected.length &&
    actual.every((key, index) => key === expected[index])
  );
}

function validStatus(value: unknown): value is TaskStatus {
  return typeof value === "string" && TASK_STATUSES.includes(value as TaskStatus);
}

function rejectDuplicateJsonKeys(source: string): void {
  let cursor = 0;

  const whitespace = () => {
    while (cursor < source.length && /[\t\n\r ]/.test(source[cursor])) {
      cursor += 1;
    }
  };

  const string = (): string => {
    const start = cursor;
    cursor += 1;

    while (cursor < source.length) {
      if (source[cursor] === "\\") {
        cursor += 2;
      } else if (source[cursor] === '"') {
        cursor += 1;
        return JSON.parse(source.slice(start, cursor)) as string;
      } else {
        cursor += 1;
      }
    }

    throw new Error("invalid JSON string");
  };

  const value = (depth: number): void => {
    if (depth > 64) throw new Error("JSON nesting is too deep");
    whitespace();

    if (source[cursor] === '"') {
      string();
      return;
    }

    if (source[cursor] === "{") {
      const seen = new Set<string>();
      cursor += 1;
      whitespace();

      while (source[cursor] !== "}") {
        const key = string();
        if (seen.has(key)) throw new Error("duplicate JSON field");
        seen.add(key);
        whitespace();
        cursor += 1; // JSON.parse already established the colon is present.
        value(depth + 1);
        whitespace();
        if (source[cursor] !== ",") break;
        cursor += 1;
        whitespace();
      }

      cursor += 1;
      return;
    }

    if (source[cursor] === "[") {
      cursor += 1;
      whitespace();

      while (source[cursor] !== "]") {
        value(depth + 1);
        whitespace();
        if (source[cursor] !== ",") break;
        cursor += 1;
        whitespace();
      }

      cursor += 1;
      return;
    }

    while (cursor < source.length && !/[\s,\]}]/.test(source[cursor])) {
      cursor += 1;
    }
  };

  value(0);
}

export async function handleDashboardStatusUpdate(
  request: Request,
  sessionId: string | null,
): Promise<Response> {
  const denied = requireDashboardIdentity(request);
  if (denied) return denied;

  if (new URL(request.url).search) {
    return dashboardResponse({ error: "task status query is not supported" }, 400);
  }

  if (request.headers.get("origin") !== new URL(request.url).origin) {
    return dashboardResponse({ error: "invalid origin" }, 403);
  }

  const contentType = request.headers
    .get("content-type")
    ?.split(";", 1)[0]
    .trim()
    .toLowerCase();

  if (contentType !== "application/json") {
    return dashboardResponse(
      { error: "content type must be application/json" },
      415,
    );
  }

  const bulk = sessionId === null;
  const maxBytes = bulk ? 65_536 : 4_096;
  const declaredLength = request.headers.get("content-length");

  if (
    declaredLength !== null &&
    (!/^\d+$/.test(declaredLength) ||
      Number(declaredLength) < 1 ||
      Number(declaredLength) > maxBytes)
  ) {
    return dashboardResponse({ error: "invalid content length" }, 400);
  }

  let body: string;

  try {
    body = await request.text();
  } catch {
    return dashboardResponse({ error: "invalid JSON body" }, 400);
  }

  const byteLength = new TextEncoder().encode(body).byteLength;

  if (byteLength < 1 || byteLength > maxBytes) {
    return dashboardResponse({ error: "invalid content length" }, 400);
  }

  let payload: unknown;

  try {
    payload = JSON.parse(body);
    rejectDuplicateJsonKeys(body);
  } catch {
    return dashboardResponse({ error: "invalid JSON body" }, 400);
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return dashboardResponse({ error: "invalid JSON body" }, 400);
  }

  const object = payload as Record<string, unknown>;
  const expectedKeys = bulk ? ["tasks", "status"] : ["expected_status", "status"];

  if (!validKeys(object, expectedKeys)) {
    return dashboardResponse(
      {
        error: bulk
          ? "bulk status update requires exactly tasks and status fields"
          : "status update requires exactly expected_status and status fields",
      },
      400,
    );
  }

  if (!validStatus(object.status) || !MUTATION_STATUSES.has(object.status)) {
    return dashboardResponse({ error: `invalid task status: ${object.status}` }, 400);
  }

  let updates: DashboardStatusUpdate[];

  if (bulk) {
    if (
      !Array.isArray(object.tasks) ||
      object.tasks.length < 1 ||
      object.tasks.length > 256
    ) {
      return dashboardResponse(
        { error: "bulk status update requires between 1 and 256 tasks" },
        400,
      );
    }

    const seen = new Set<string>();
    updates = [];

    for (const item of object.tasks) {
      if (
        !item ||
        typeof item !== "object" ||
        Array.isArray(item) ||
        !validKeys(item as Record<string, unknown>, [
          "session_id",
          "expected_status",
        ])
      ) {
        return dashboardResponse(
          {
            error:
              "each bulk task requires exactly session_id and expected_status fields",
          },
          400,
        );
      }

      const candidate = item as Record<string, unknown>;

      if (
        typeof candidate.session_id !== "string" ||
        !candidate.session_id ||
        candidate.session_id.length > 256
      ) {
        return dashboardResponse({ error: "invalid task session id" }, 400);
      }

      if (seen.has(candidate.session_id)) {
        return dashboardResponse({ error: "duplicate task session id" }, 400);
      }

      if (!validStatus(candidate.expected_status)) {
        return dashboardResponse(
          { error: `invalid expected task status: ${candidate.expected_status}` },
          400,
        );
      }

      seen.add(candidate.session_id);
      updates.push({
        session_id: candidate.session_id,
        expected_status: candidate.expected_status,
      });
    }
  } else {
    if (!validStatus(object.expected_status)) {
      return dashboardResponse(
        { error: `invalid expected task status: ${object.expected_status}` },
        400,
      );
    }

    updates = [{ session_id: sessionId, expected_status: object.expected_status }];
  }

  try {
    const result = await updateDashboardTaskStatuses(updates, object.status);

    return dashboardResponse(
      bulk ? result : { changed: result.changed, task: result.tasks[0] },
    );
  } catch (error) {
    return dashboardError(error);
  }
}
