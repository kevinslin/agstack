CREATE TABLE `agtask_rollouts` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`created` text NOT NULL,
	`thread_id` text NOT NULL,
	`turn_id` text NOT NULL,
	`role` text NOT NULL,
	`message` text NOT NULL,
	FOREIGN KEY (`thread_id`) REFERENCES `agtask_threads`(`id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "agtask_rollouts_role_check" CHECK("agtask_rollouts"."role" in ('user', 'assistant', 'meta')),
	CONSTRAINT "agtask_rollouts_message_check" CHECK(length("agtask_rollouts"."message") between 1 and 240)
);
--> statement-breakpoint
CREATE INDEX `agtask_rollouts_thread_order_idx` ON `agtask_rollouts` (`thread_id`,`created`,`id`);--> statement-breakpoint
CREATE UNIQUE INDEX `agtask_rollouts_event_idx` ON `agtask_rollouts` (`thread_id`,`role`,`turn_id`);--> statement-breakpoint
CREATE TABLE `agtask_threads` (
	`id` text PRIMARY KEY NOT NULL,
	`session_id` text NOT NULL,
	`parent_session_id` text,
	`kind` text NOT NULL,
	`project` text NOT NULL,
	`title` text NOT NULL,
	`description` text DEFAULT '' NOT NULL,
	`created` text NOT NULL,
	`updated` text NOT NULL,
	`closed` text,
	`status` text NOT NULL,
	CONSTRAINT "agtask_threads_id_check" CHECK(length("agtask_threads"."id") > 0),
	CONSTRAINT "agtask_threads_session_id_check" CHECK(length("agtask_threads"."session_id") > 0),
	CONSTRAINT "agtask_threads_project_check" CHECK(length(trim("agtask_threads"."project")) > 0),
	CONSTRAINT "agtask_threads_status_check" CHECK("agtask_threads"."status" in ('todo', 'active', 'blocked', 'merging', 'done', 'drop')),
	CONSTRAINT "agtask_threads_closed_check" CHECK(("agtask_threads"."status" in ('done', 'drop') and "agtask_threads"."closed" is not null) or ("agtask_threads"."status" not in ('done', 'drop') and "agtask_threads"."closed" is null)),
	CONSTRAINT "agtask_threads_parent_check" CHECK(("agtask_threads"."kind" = 'main' and "agtask_threads"."parent_session_id" is null) or ("agtask_threads"."kind" = 'child' and "agtask_threads"."parent_session_id" is not null and "agtask_threads"."parent_session_id" != "agtask_threads"."session_id")),
	CONSTRAINT "agtask_threads_description_check" CHECK(length("agtask_threads"."description") <= 240)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `agtask_threads_session_id_idx` ON `agtask_threads` (`session_id`);--> statement-breakpoint
CREATE INDEX `agtask_threads_status_updated_idx` ON `agtask_threads` (`status`,`updated`);--> statement-breakpoint
CREATE INDEX `agtask_threads_parent_session_idx` ON `agtask_threads` (`parent_session_id`);