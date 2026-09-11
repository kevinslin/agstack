# Remote project registration

Use this reference when a user asks Codex to add or verify a remote saved
project. Registration makes the Codex app know about an existing remote folder;
it does not clone a repository, create a DevBox, repair SSH, or make a remote
workspace leasable by itself.

## Preferred path

Use a first-party project-registration tool when the current Codex app exposes
one. Pass the intended label, host, and one remote source path. Verify the
returned saved project with a fresh project listing before reporting success.

If the tool is not exposed, use the config import path below.

## Config import path

1. Verify the intended SSH alias and remote directory with existing
   authentication. Use the user's normal interactive environment when their
   shell config matters. Do not alter credentials or SSH configuration unless the
   user explicitly requested that separate repair.
2. Read the current saved projects with `list_projects`. Skip registration when
   the exact host and remote path are already saved.
3. Resolve the running app's `CODEX_HOME` (normally `~/.codex`) and back up
   `codex-app/config.json` beneath it. If absent, start with version 1 and an
   empty `remoteConnections` array.
4. Merge the requested project into the existing config. Preserve unrelated
   fields and existing remote connections. The minimum remote declaration is:

   ```json
   {
     "version": 1,
     "remoteConnections": [
       {
         "sshAlias": "example-host",
         "projects": [
           {
             "remotePath": "/home/user/code",
             "label": "code"
           }
         ]
       }
     ]
   }
   ```

5. Batch verified additions into one write. Confirm the file has not changed
   since reading it, write the merged JSON atomically, then run on macOS:

   ```bash
   /usr/bin/open 'codex://codex-app/apply-config'
   ```

6. If the app asks for folder or connection consent, honor the app prompt. Do
   not bypass consent by editing private app state files.
7. Allow for asynchronous import and check `list_projects` with bounded,
   spaced retries (up to two minutes). Report success only when the expected
   host and remote path appear with a saved project ID. Keep existing IDs
   unchanged. On timeout, inspect the app result or report pending consent or
   connection errors; do not repeatedly apply the file or invent project IDs.

## Internal behavior and boundaries

The import resolves SSH aliases, creates missing saved remote projects, and
preserves existing project IDs for normalized host/path matches. Verify directory
existence separately in preflight. It applies the entire file and can connect
other declared remotes, so preserve existing declarations and preferences.
Reapplying the same config should not create duplicate saved projects for the
same normalized host/path.

Do not edit Codex's private global state files directly. Direct state edits skip
validation, consent, project ordering, declaration tracking, and window
broadcasts, and can race with the running app.

The config declaration is an input to the app import process. A backup restores
the declaration file, but it does not delete saved projects that the app already
created. If a rollback is needed, use a supported app path for removal.

Registration is separate from leasing or task creation. A bare non-Git remote
folder can be a saved project, but lease workflows that require Git still need a
verified Git checkout inside the saved project.
