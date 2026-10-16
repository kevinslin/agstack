import { sql } from "drizzle-orm";
import {
  check,
  index,
  integer,
  sqliteTable,
  text,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

export const probeState = sqliteTable("probe_state", {
  id: integer("id").primaryKey(),
  message: text("message").notNull(),
  updatedAt: text("updated_at").notNull(),
});

export const agtaskThreads = sqliteTable(
  "agtask_threads",
  {
    id: text("id").primaryKey(),
    sessionId: text("session_id").notNull(),
    parentSessionId: text("parent_session_id"),
    kind: text("kind", { enum: ["main", "child"] }).notNull(),
    project: text("project").notNull(),
    title: text("title").notNull(),
    description: text("description").notNull().default(""),
    created: text("created").notNull(),
    updated: text("updated").notNull(),
    closed: text("closed"),
    status: text("status", {
      enum: ["todo", "active", "blocked", "merging", "done", "drop"],
    }).notNull(),
  },
  (table) => [
    uniqueIndex("agtask_threads_session_id_idx").on(table.sessionId),
    index("agtask_threads_status_updated_idx").on(table.status, table.updated),
    index("agtask_threads_parent_session_idx").on(table.parentSessionId),
    check("agtask_threads_id_check", sql`length(${table.id}) > 0`),
    check(
      "agtask_threads_session_id_check",
      sql`length(${table.sessionId}) > 0`,
    ),
    check(
      "agtask_threads_project_check",
      sql`length(trim(${table.project})) > 0`,
    ),
    check(
      "agtask_threads_status_check",
      sql`${table.status} in ('todo', 'active', 'blocked', 'merging', 'done', 'drop')`,
    ),
    check(
      "agtask_threads_closed_check",
      sql`(${table.status} in ('done', 'drop') and ${table.closed} is not null) or (${table.status} not in ('done', 'drop') and ${table.closed} is null)`,
    ),
    check(
      "agtask_threads_parent_check",
      sql`(${table.kind} = 'main' and ${table.parentSessionId} is null) or (${table.kind} = 'child' and ${table.parentSessionId} is not null and ${table.parentSessionId} != ${table.sessionId})`,
    ),
    check(
      "agtask_threads_description_check",
      sql`length(${table.description}) <= 240`,
    ),
  ],
);

export const agtaskRollouts = sqliteTable(
  "agtask_rollouts",
  {
    id: integer("id").primaryKey({ autoIncrement: true }),
    created: text("created").notNull(),
    threadId: text("thread_id")
      .notNull()
      .references(() => agtaskThreads.id, { onDelete: "cascade" }),
    turnId: text("turn_id").notNull(),
    role: text("role", { enum: ["user", "assistant", "meta"] }).notNull(),
    message: text("message").notNull(),
  },
  (table) => [
    index("agtask_rollouts_thread_order_idx").on(
      table.threadId,
      table.created,
      table.id,
    ),
    uniqueIndex("agtask_rollouts_event_idx").on(
      table.threadId,
      table.role,
      table.turnId,
    ),
    check(
      "agtask_rollouts_role_check",
      sql`${table.role} in ('user', 'assistant', 'meta')`,
    ),
    check(
      "agtask_rollouts_message_check",
      sql`length(${table.message}) between 1 and 240`,
    ),
  ],
);
