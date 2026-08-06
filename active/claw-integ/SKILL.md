---
name: claw-integ
description: Run live OpenClaw integration proof against a named claw gateway profile with showboat-v2.
dependencies:
  - mem
  - showboat-v2
---

# claw-integ

Use this skill when the user invokes `$claw-integ` to prove OpenClaw behavior against a live claw gateway profile.

Usage:

```text
$claw-integ [profile] "test it"
```

`profile` is optional. When omitted, infer the profile from the behavior under test.

## Contract

Run a live integration proof through the requested claw gateway profile and capture the evidence with `../showboat-v2/SKILL.md`.

Do not use Showboat to wrap existing unit tests. The proof must exercise the expected behavior through the live gateway/TUI or the closest repo-supported live gateway client path.

When testing exec or plugin approvals, read `./references/approvals.md` before starting the live run.

When testing Signal channel delivery or Signal-backed approvals, read `./references/signal.md` before starting the live run.

When testing iMessage or SMS-backed approvals, read `./references/imessage.md` before starting the live run.

## Approval Proof Matrix

When the live run tests exec or plugin approval delivery, create a row-by-row proof matrix before triggering requests. The proof is incomplete until every user-requested row is either observed with artifacts or recorded with a specific blocker.

Include rows for the relevant approval family and channel states:

- delivery enabled: request is delivered to the expected channel surface.
- reaction or native action: the requested decision resolves as expected.
- manual `/approve`: `allow-always` or any requested slash-command fallback works when applicable.
- delivery disabled: no approval request is delivered to that channel and fallback is not suppressed.
- unauthorized actor: the attempted reaction/action does not resolve the approval.
- negative reaction/input: unsupported reactions or stale inputs do not resolve the approval when the user asked for that case.

For each row, record the exact command or live action, expected result, observed result, raw artifact path, and screenshot/photo path when the user asks for visual proof. Do not summarize the approval suite as complete from unit tests alone.

## Serialized Live-Turn Contract

Treat channel-backed integration as a state machine, not merely an ordered list:

```text
parent-created -> turn-active -> terminal-reply
terminal-reply -> approval-pending -> decision-or-expiry -> terminal-reply
terminal-reply -> direct-side-effect-verification -> next-scenario
```

- Use the exact first scenario as the top-level bot mention. Do not create a generic starter and immediately add the real scenario as a reply.
- Keep checklists, progress notes, headings, and summaries in the proof directory while the run is active. Do not post control/report messages into the tested channel or thread until every scenario is terminal.
- Do not send the next scenario until the prior same-thread turn has a terminal bot reply and no pending approval or active work remains.
- Persist parent/reply timestamps, nonce, approval ID, expiry, state transition, and direct verification result under `<proof-root>/raw/` as the run progresses.
- For approval turns, follow the stricter lifecycle and expiry recovery rules in `./references/approvals.md`.

## Profile Selection

1. Resolve the OpenClaw repo root.
   - Prefer the current git root when it is the OpenClaw repo.
   - Otherwise use `/Users/kevinlin/code/openclaw` unless the user gives another path.
2. Select exactly one local claw integration profile:
   - `openclaw-codex-dev`: Codex claw profile. Use it for Codex harness, Codex app-server, Codex plugin/tool, Codex approval, or OpenAI Codex runtime/protocol behavior.
   - `.openclaw-dev`: dev claw profile. Use it for the normal OpenClaw dev gateway/TUI path, Pi-style harness work, non-Codex channel delivery, and generic OpenClaw behavior.
3. If the user passes no profile, infer the profile from the requested test:
   - choose `openclaw-codex-dev` only when the behavior being tested depends on Codex;
   - otherwise choose `.openclaw-dev`.
4. If the user passes a profile, use it only when it is one of the two valid profiles above. If another profile is requested, stop and ask which valid profile should be used.
5. Do not create ad hoc profiles, clone `.openclaw-dev`, or copy credentials between profiles.
6. Do not print secrets, auth tokens, refresh tokens, or provider credentials.

Treat these as local claw profile selectors, not always as literal `OPENCLAW_PROFILE` values. Before invoking OpenClaw commands, resolve and record the selected profile's concrete OpenClaw runtime environment, including the actual `OPENCLAW_PROFILE`, `OPENCLAW_STATE_DIR`, and `OPENCLAW_CONFIG_PATH` when present. For `.openclaw-dev`, the OpenClaw dev CLI profile is `dev` and the state directory is `~/.openclaw-dev`; do not pass `.openclaw-dev` as `OPENCLAW_PROFILE`.

Profile existence is a local state check: the selected claw profile exists only when its matching local config/state can be found and the resolved OpenClaw config path points at `openclaw.json`. Prefer profile-aware CLI commands for operation, but use the resolved state/config paths for existence checks and redacted summaries.

## Remote Target Routing

This skill's built-in profile contract is local-only. When the user requests a remote gateway or hosted tenant:

1. Do not reinterpret it as `openclaw-codex-dev` or `.openclaw-dev`.
2. Route to an explicitly available environment-specific remote integration workflow when one exists.
3. Require that workflow to preserve this skill's proof matrix, serialized live-turn contract, Showboat artifacts, screenshots, direct side-effect verification, and applicable completion criteria.
4. If no remote workflow is available or the remote target is ambiguous, stop before sending live traffic and record the blocker.

Do not add remote credentials, tenant paths, or provider-specific cluster assumptions to this public skill.

## Gateway Setup

Use the selected profile's claw gateway. Prefer repo-local or documented profile-aware commands over ad hoc global state changes.

Before running the proof:

1. Confirm the gateway profile config points at the intended profile.
2. Confirm the gateway is running or start/restart it with the repo-supported command.
3. Record a redacted config summary in the proof, including:
   - profile name
   - gateway URL or port
   - enabled OpenClaw plugin/extension relevant to the test
   - destructive-action or approval settings relevant to the test
4. If the test needs a specific app/plugin setup, use the product migration or setup command that the profile would use in production. Do not manually symlink plugin/cache/auth files unless the user explicitly asks.

For `.openclaw-dev`, use the dev profile and dev gateway/TUI path:

```sh
pnpm gateway:dev
pnpm tui:dev
```

For `openclaw-codex-dev`, first resolve the profile's concrete OpenClaw environment from the local claw profile config/service env, then use profile-scoped commands from the repo root:

```sh
OPENCLAW_PROFILE=<resolved-openclaw-profile> pnpm openclaw gateway status --deep --require-rpc
OPENCLAW_PROFILE=<resolved-openclaw-profile> pnpm openclaw gateway restart
OPENCLAW_PROFILE=<resolved-openclaw-profile> pnpm openclaw tui
```

For every `openclaw-codex-dev` run, confirm the Google Calendar Codex plugin is configured and enabled before the live invocation. The redacted config summary must show:

- `plugins.entries.codex.enabled: true`
- `plugins.entries.codex.config.codexPlugins.enabled: true`
- `plugins.entries.codex.config.codexPlugins.plugins["google-calendar"].enabled: true`
- `marketplaceName: "openai-curated"`
- `pluginName: "google-calendar"`

If the `google-calendar` entry exists but is disabled, enable it through the product-supported Codex command:

```text
/codex plugins enable google-calendar
```

If the entry is missing, use the Codex migration/setup flow for the selected profile before the live run:

```sh
OPENCLAW_PROFILE=<resolved-openclaw-profile> pnpm openclaw migrate apply codex --yes --plugin google-calendar
```

After changing `codexPlugins`, start a fresh Codex conversation with `/new` or `/reset` before testing plugin behavior. Do not treat `openclaw-codex-dev` proof as ready until Google Calendar is enabled or a specific blocker is recorded.

If the test needs Codex plugins, ensure the selected profile has the required `allow_destructive_actions` or equivalent policy before the live invocation, and record the redacted setting in the proof.

## Existing App Approval Runs

When testing approvals through an existing channel app such as WhatsApp, Signal, iMessage, SMS, or a browser-backed sender, do this preflight before sending the first live message:

1. Confirm the requested harness and runtime path.
   - If the user asks for Pi harness, verify the profile config is not pointing at the Codex app server.
   - If the user asks for Codex harness, verify the app-server path intentionally points at Codex.
   - Record the redacted harness/app-server summary before changing anything.
2. Confirm the selected profile's concrete state path.
   - Valid local claw profiles are only `openclaw-codex-dev` and `.openclaw-dev`.
   - `.openclaw-dev` resolves to OpenClaw profile `dev` and state path `~/.openclaw-dev`.
   - `openclaw-codex-dev` must be resolved from its local profile config/service env before launch.
   - Use user-provided profile instructions as runtime input; do not bake profile-specific paths into scenario docs.
3. Confirm the requested launch surface.
   - If the user asks for iTerm or another visible app launch, use that surface for the live run.
   - Do not switch to LaunchAgent, tmux, or a background service for an existing-app proof unless the user explicitly asks.
4. Confirm the target channel and plugin are active in the selected profile.
   - Record the enabled channel/plugin ids, relevant approval config, and any installed local plugin path in redacted form.
   - For plugin approval tests, confirm the plugin is installed and enabled before sending a message that asks the model to call it.
5. Use one nonce per row and carry it through the outbound message, logs, screenshots, and proof matrix.

Split every approval row into two gates:

- request-created gate: prove the approval request exists before attempting to approve or deny it.
- decision gate: only after the request exists, prove accept and deny resolve the expected pending request.

For plugin approvals, the request-created gate must include evidence that the plugin call actually reached the approval path, such as `plugin.approval.waitDecision`, a pending item from `plugin.approval.list`, or the equivalent channel/runtime artifact. If the model sends a normal reply without calling the plugin, record that as a plugin-invocation blocker rather than testing accept or deny.

For exec approvals, similarly prove the exec approval request exists before acting on it. Do not infer plugin approval health from exec approval success; they use different approval namespaces and may fail independently.

Keep log collection narrow. Search by nonce, channel session id, request id, or the selected profile's known log/session files. Avoid broad recursive scans of the entire profile directory when it can include caches, `node_modules`, or old session artifacts.

## Video Proof

Capture video proof with `ffmpeg` for every live `$claw-integ` run when feasible.

Store video artifacts under `<proof-root>/raw/`:

- `<scenario-slug>.mp4`: the proof video
- `<scenario-slug>.ffprobe.txt`: `ffprobe` metadata for the MP4
- `<scenario-slug>.video-notes.md`: capture method, command, duration, and any cropping/redaction notes

Start recording before the live action and stop only after the expected result is visible. Include the video and `ffprobe` files in the Showboat raw artifact index and scenario result.

For terminal, prompt, menu, or TUI behavior, prefer privacy-safe tmux-pane video over full desktop capture:

1. Drive the interaction through `tmux`.
2. Capture pane snapshots during the run into `raw/<scenario-slug>.frames/` or an equivalent temporary frame directory.
3. Render those snapshots to images if needed.
4. Encode the frames with `ffmpeg`:

```sh
ffmpeg -hide_banner -y -framerate 1 \
  -i "<frames-dir>/frame_%04d.png" \
  -c:v libx264 -pix_fmt yuv420p -r 30 -movflags +faststart \
  "<proof-root>/raw/<scenario-slug>.mp4"
```

For browser or graphical UI behavior that cannot be proven from tmux output, use `ffmpeg` screen capture with the narrowest feasible capture area. Avoid recording unrelated private windows. On macOS, first list devices:

```sh
ffmpeg -hide_banner -f avfoundation -list_devices true -i ""
```

Then capture the intended screen only, adding crop filters when needed:

```sh
ffmpeg -hide_banner -y -f avfoundation -framerate 30 \
  -i "<screen-index>:none" \
  -c:v libx264 -pix_fmt yuv420p -movflags +faststart \
  "<proof-root>/raw/<scenario-slug>.mp4"
```

Verify every produced video:

```sh
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,duration,nb_frames \
  -of default=noprint_wrappers=1 \
  "<proof-root>/raw/<scenario-slug>.mp4" \
  > "<proof-root>/raw/<scenario-slug>.ffprobe.txt"
```

If `ffmpeg` is unavailable, screen-recording permission is blocked, or recording would expose unrelated private content, save blocker evidence under `raw/`, keep the non-video Showboat proof intact, and report the gap directly.

## Inline Screenshot Proof

For live integration proof, the conversation itself must include image proof, not only a path, PR link, video, or Showboat artifact.

Capture at least one still screenshot of the actual channel surface being tested and store it under `<proof-root>/raw/`:

- TUI or terminal proof: capture the tmux pane or terminal window showing the tested prompt/result.
- WhatsApp, Telegram, Slack, Discord, Matrix, browser, or app proof: capture the real channel/app surface showing the tested message, approval, reaction, reply, or resolved state.
- Approval proof: include both the approval request and the visible resolved/denied/allowed state when feasible.

Before final handoff, show that screenshot inline in the thread using the chat surface's supported image mechanism. If a local path will not render inline, upload or attach the redacted screenshot through an approved artifact/image path and embed that image. The final answer must also name the saved raw screenshot path.

If screenshot capture or inline display is blocked, the integration proof is incomplete for user-facing purposes. Save blocker evidence under `raw/`, state the blocker directly, and do not imply that full proof was shown inline.

## Showboat Proof

Use `../showboat-v2/SKILL.md` for every `$claw-integ` run.

The proof directory is a durable artifact. Before choosing the proof path, invoke `../mem/SKILL.md` and resolve the OpenClaw memory base, root, schemas, and file rules. Do not infer the target from a cwd-relative `.mem` path; `$mem` may resolve to any configured folder. If `$mem` cannot resolve a suitable OpenClaw proof base, ask before falling back to a workspace-local proof directory.

Use these OpenClaw-specific values with `showboat-v2`:

- `<proofs-root>`: the concrete root/path resolved from the aggregate `$mem` base `claw` and its schema-owned proofs placement, otherwise the explicitly approved fallback proof root.
- `<proof-slug>`: `demo-{num}-{profile}-{slug}`.
- `<proof-root>`: `<proofs-root>/<proof-slug>`.
- `<scenario-slug>`: a short behavior slug; use one scenario file per distinct behavior path.

Report the selected `$mem` base name, resolved root, and final `<proof-root>` in the handoff so wrong-root writes are auditable.

Follow `showboat-v2` to materialize `proof.md` and each `scenario/<scenario-slug>.md`, create `raw/` and `scripts/`, and capture the stable Showboat summary at:

```text
<proof-root>/raw/showboat-summary.md
```

The proof must include:

1. `proof.md` with the claim, expected behavior, target details, status, scenario results, and raw artifact index.
2. At least one `scenario/<scenario-slug>.md` describing the requested profile, test prompt, preconditions, relevant redacted config, live action, expected result, observed result, and raw artifact links.
3. The exact setup or migration command used for required live apps/plugins.
4. The live gateway/TUI invocation or gateway request that exercises the behavior.
5. A deterministic summary of the observed result.
6. Video proof and `ffprobe` metadata under `raw/`, or explicit blocker evidence if video capture was not feasible.
7. At least one still screenshot of the tested channel surface under `raw/`, plus inline display of that screenshot in the conversation before final handoff.
8. Raw nondeterministic output under `raw/`, not embedded directly in a way that breaks `showboat verify`.
9. A final `uvx showboat verify <proof-root>/raw/showboat-summary.md` pass.

When the output includes timestamps, temp paths, session ids, event ids, or stochastic model text, save raw output under `raw/` and capture a stable summary command in the verified Showboat summary.

## Missing or Invalid Profiles

When the selected local claw profile is missing, ambiguous, or not one of `openclaw-codex-dev` / `.openclaw-dev`:

1. Stop before starting the gateway or sending any live message.
2. Record the blocker in the proof directory if one has already been created.
3. Ask the user which valid profile to use or ask them to repair the missing local profile.
4. Do not copy `.openclaw-dev`, create a new profile, or move credentials as part of `claw-integ`.

## Completion Criteria

For built-in local-profile runs, the run is complete only when:

- the requested profile was selected from `openclaw-codex-dev` or `.openclaw-dev`
- the claw gateway for that profile was used
- the requested behavior was exercised live
- every channel turn followed the serialized live-turn contract and no control/report message raced a scenario
- ffmpeg video proof was captured under `raw/`, or a video-capture blocker was saved there
- a still screenshot of the tested channel surface was saved under `raw/` and shown inline in the conversation, or a screenshot/inline-display blocker was saved and reported
- the `showboat-v2` proof directory was materialized and filled
- `uvx showboat verify <proof-root>/raw/showboat-summary.md` passed
- the final answer reports the proof directory, profile used, observed result, and any untested gaps

If any step is blocked, save the partial proof directory with the blocker evidence and report the blocker directly.
