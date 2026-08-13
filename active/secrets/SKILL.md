---
name: secrets
description: Load local dotenvx credential sets for agent workflows.
dependencies: []
---

# Secrets

Use this skill to load local credential sets into agent-run commands without printing or copying secret values into chat.

Credential files live under:

```text
~/.secrets/.env.{name}[.{stage}]
```

Examples:

- `$secrets slack` uses `~/.secrets/.env.slack`.
- `$secrets chat.prod` uses `~/.secrets/.env.chat.prod`.
- `$secrets init foo` creates `~/.secrets/.env.foo`.

Manage values with `dotenvx`. Do not hand-edit encrypted values unless the user explicitly wants plaintext local env files.

## Safety Rules

- Never print, summarize, paste, commit, screenshot, or log secret values.
- Never run broad dumps such as `env`, `printenv`, `set`, or `dotenvx decrypt` after loading real credentials.
- Do not quote command output that may include credentials. Redact first, or summarize only non-secret status.
- Treat anything printed into the transcript as exposed. If a secret is exposed, tell the user to rotate it.
- Keep `~/.secrets` private: create it with mode `700` and env files with mode `600`.
- Prefer `dotenvx run --no-armor --no-native --no-1password --no-bitwarden -f <file> -- <command>` so secrets stay scoped to one subprocess without invoking external secret integrations.

## Commands

Use the bundled helper from this skill directory:

```bash
./scripts/secrets <name>[.<stage>] [-- command ...]
./scripts/secrets init <name>[.<stage>]
./scripts/secrets path <name>[.<stage>]
```

If running from outside the skill directory, resolve the helper relative to `SKILL.md`; do not assume it is on `PATH`.

### Load a Credential Set

When the user invokes:

```text
$secrets slack
```

Resolve the file:

```bash
./scripts/secrets path slack
```

Then run commands that need those credentials through dotenvx:

```bash
./scripts/secrets slack -- <command>
```

If the user has not provided a command yet, report that `slack` maps to `~/.secrets/.env.slack` and ask for or infer the next command that needs the credentials. In an interactive shell session, `./scripts/secrets slack` opens a subshell under `dotenvx`.

### Load a Staged Credential Set

When the user invokes:

```text
$secrets chat.prod
```

Use:

```bash
./scripts/secrets chat.prod -- <command>
```

This maps directly to `~/.secrets/.env.chat.prod`. Dots are part of the credential-set name, so do not reinterpret `prod` as a separate flag.

### Initialize a Credential File

When the user invokes:

```text
$secrets init foo
```

Run:

```bash
./scripts/secrets init foo
```

This creates `~/.secrets` if needed and creates `~/.secrets/.env.foo` if missing. It intentionally does not write placeholder credentials.

Add or update values with dotenvx:

```bash
dotenvx set API_TOKEN "<value>" -f ~/.secrets/.env.foo
```

Do not put real values in chat. If the value is not already available through a safe local mechanism, ask the user to run the `dotenvx set` command themselves.

## Usage Patterns

### Run one command

```bash
./scripts/secrets slack -- slack-cli auth test
```

### Start a scoped shell

Use this only when multiple follow-up commands need the same credentials and the shell session will stay local:

```bash
./scripts/secrets chat.prod
```

Avoid running commands inside that shell that print all environment variables.

### Use dotenvx directly

The helper is thin. If a command needs a custom option, call dotenvx directly:

```bash
dotenvx run --no-armor --no-native --no-1password --no-bitwarden -f ~/.secrets/.env.chat.prod -- <command>
```

For a non-default keys file:

```bash
dotenvx run --no-armor --no-native --no-1password --no-bitwarden -f ~/.secrets/.env.chat.prod -fk ~/.secrets/.env.keys -- <command>
```

## Troubleshooting

- If `dotenvx` is missing, install it before using this skill: `npm install @dotenvx/dotenvx --global`.
- If the env file is missing, run `./scripts/secrets init <name>[.<stage>]`.
- If decrypting fails, check that the matching `.env.keys` or `DOTENV_PRIVATE_KEY_*` value is available locally, but do not print either one.
- If the target command fails auth, verify only non-secret facts: file path, command shape, variable names expected by the tool, and whether dotenvx reported an injection error.
- If a command needs a credential under a different variable name, use `dotenvx set NEW_NAME "<value>" -f ~/.secrets/.env.<name>` rather than exporting aliases in shell history.
