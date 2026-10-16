import { env } from "cloudflare:workers";
import { executeTaskOperation, TaskOperationError } from "@/db/agtask";

const MAX_BODY_BYTES = 16 * 1024;

function matchesTaskBearer(authorization: string | null): boolean {
  const secret = Reflect.get(env, "AGTASK_TASKS_SECRET");

  if (typeof secret !== "string" || secret.length === 0 || !authorization) {
    return false;
  }

  const expected = `Bearer ${secret}`;

  if (authorization.length !== expected.length) {
    return false;
  }

  let difference = 0;

  for (let index = 0; index < expected.length; index += 1) {
    difference |= authorization.charCodeAt(index) ^ expected.charCodeAt(index);
  }

  return difference === 0;
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ operation: string }> },
) {
  if (!matchesTaskBearer(request.headers.get("authorization"))) {
    return Response.json(
      { error: "A valid task bearer token is required." },
      {
        status: 401,
        headers: { "www-authenticate": 'Bearer realm="agtask"' },
      },
    );
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");

  if (!Number.isFinite(declaredLength) || declaredLength > MAX_BODY_BYTES) {
    return Response.json({ error: "The request body is too large." }, { status: 413 });
  }

  let body: string;

  try {
    body = await request.text();
  } catch {
    return Response.json({ error: "The request body could not be read." }, { status: 400 });
  }

  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    return Response.json({ error: "The request body is too large." }, { status: 413 });
  }

  let payload: unknown;

  try {
    payload = JSON.parse(body);
  } catch {
    return Response.json({ error: "A valid JSON object is required." }, { status: 400 });
  }

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return Response.json({ error: "A valid JSON object is required." }, { status: 400 });
  }

  try {
    const { operation } = await params;
    const result = await executeTaskOperation(
      operation,
      payload as Record<string, unknown>,
    );

    return Response.json(result, {
      headers: { "cache-control": "no-store" },
    });
  } catch (error) {
    if (error instanceof TaskOperationError) {
      return Response.json({ error: error.message }, { status: error.status });
    }

    return Response.json({ error: "Task storage is unavailable." }, { status: 503 });
  }
}
