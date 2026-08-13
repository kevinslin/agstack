import { env } from "cloudflare:workers";
import { readProbe, writeProbe } from "@/db/probe";

const MAX_BODY_BYTES = 4096;
const MAX_MESSAGE_LENGTH = 280;

function platformIdentity(request: Request) {
  return {
    identityPresent: Boolean(request.headers.get("oai-authenticated-user-id")),
    platformHeaderForwarded: Boolean(
      request.headers.get("oai-sites-authorization"),
    ),
  };
}

function matchesBearerSecret(authorization: string | null): boolean {
  const secret = Reflect.get(env, "AGTASK_PROBE_SECRET");

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

export async function GET(request: Request) {
  try {
    return Response.json(
      { probe: await readProbe(), ...platformIdentity(request) },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return Response.json({ error: "Probe storage is unavailable." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  if (!matchesBearerSecret(request.headers.get("authorization"))) {
    return Response.json(
      { error: "A valid probe bearer token is required." },
      {
        status: 401,
        headers: { "www-authenticate": 'Bearer realm="agtask-probe"' },
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

  const message =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? Reflect.get(payload, "message")
      : undefined;

  if (
    typeof message !== "string" ||
    message.trim().length === 0 ||
    message.length > MAX_MESSAGE_LENGTH
  ) {
    return Response.json(
      { error: `message must contain 1 to ${MAX_MESSAGE_LENGTH} characters.` },
      { status: 400 },
    );
  }

  try {
    return Response.json(
      { probe: await writeProbe(message.trim()), ...platformIdentity(request) },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return Response.json({ error: "Probe storage is unavailable." }, { status: 503 });
  }
}
