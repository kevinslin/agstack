---
name: dev.codex
description: Manage Codex self-configuration, remote saved projects, and session analysis; not skill authoring (use $sc).
dependencies: []
---

# dev.codex

## Overview
Use this skill to manage Codex's own configuration and runtime setup. Start with MCP
server management; expand with new capabilities as needed.

## Core capabilities

### 1. MCP management
- Use when asked to add, remove, or update MCP servers or edit Codex MCP settings.
- Read `./references/mcp-management.md` for CLI syntax and config options from the docs.
- Prefer the CLI for adding servers; edit `~/.codex/config.toml` for fine-grained config.
- Remove a server by deleting its `[mcp_servers.<server-name>]` table or set
  `enabled = false` to disable.
- Confirm the active set via `/mcp` in the Codex TUI or by inspecting the config file.

### 2. Remote saved project registration
- Use when asked to add or verify a remote project in the Codex app.
- Read `./references/remote-project-registration.md` before changing app config.
- Prefer an exposed Codex project-registration tool when one is available. If it is
  unavailable, use the supported config import flow.
- Back up and merge `$CODEX_HOME/codex-app/config.json`; do not edit private
  app state files directly.
- Apply config with the Codex app deep link, then verify with a fresh saved-project
  listing. Do not treat the deep-link exit code as proof that registration finished.

### 3. Session summaries (by session id)
- Use when the user provides a Codex session id and asks for a summary of that session.
- If the user needs help finding or mapping session ids, use the `dev.llm-session` skill.
- Locate the session data under `~/.codex/sessions/` (preferred) or
  `~/.codex/history.jsonl` and load only the relevant session.
- Summarize with: time range, primary goals, key actions/commands, decisions,
  errors/blocks, and concrete next steps.
- Redact or avoid sensitive data; include short code paths/filenames only when they
  are essential to the summary.

### 4. Multi-agent role management (add/update agents)
- Use when asked to add, update, or tune Codex sub-agent roles.
- Source of truth: `https://developers.openai.com/codex/multi-agent/`.
- Ensure multi-agent is enabled first:
  - Enable via `/experimental` in Codex CLI and restart, or set:
    ```toml
    [features]
    multi_agent = true
    ```
- Configure roles in `[agents]` in either:
  - `~/.codex/config.toml` for personal defaults.
  - `.codex/config.toml` for project-shared roles.
- Add or update role entries as `[agents.<name>]` with:
  - `description`: short guidance for when Codex should choose the role.
  - `config_file`: TOML layer for that role (relative paths resolve from the owning
    `config.toml`).
- Create or update each role `config_file` to set role-specific overrides such as:
  - `model`, `model_reasoning_effort`, `sandbox_mode`, `developer_instructions`.
  - Optional role-local MCP and skills settings when needed.
- Important validation and behavior:
  - Unknown keys in `[agents.<name>]` are rejected.
  - `config_file` must exist and load cleanly or role spawns can fail.
  - If a custom role name matches a built-in role (`default`, `worker`,
    `explorer`, `monitor`), the custom role takes precedence.
  - Unset settings inherit from the parent session.
  - `agents.max_depth` defaults to `1` (child can spawn, deeper nesting blocked).
- Verify changes by restarting Codex, then:
  - Use `/agent` to inspect/switch active agent threads in CLI.
  - Spawn explicitly with `agent_type = "<name>"` when testing a role.
