import { env } from "cloudflare:workers";

export interface ProbeValue {
  message: string;
  updatedAt: string;
}

function getProbeDatabase() {
  if (!env.DB) {
    throw new Error("The required Cloudflare D1 binding DB is unavailable.");
  }

  return env.DB;
}

export async function readProbe(): Promise<ProbeValue | null> {
  return getProbeDatabase()
    .prepare(
      `SELECT message, updated_at AS updatedAt
       FROM probe_state
       WHERE id = 1`,
    )
    .first<ProbeValue>();
}

export async function writeProbe(message: string): Promise<ProbeValue> {
  const updatedAt = new Date().toISOString();

  await getProbeDatabase()
    .prepare(
      `INSERT INTO probe_state (id, message, updated_at)
       VALUES (1, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         message = excluded.message,
         updated_at = excluded.updated_at`,
    )
    .bind(message, updatedAt)
    .run();

  return { message, updatedAt };
}
