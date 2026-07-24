# Knowledge workflow

Use these rules after `$mem` selects a managed base and resolves its schemas.

## Project context lookup

Use this mode when project or workspace instructions require `$mem` to orient source work, even when the user did not request a durable write.

1. Inspect the resolved schemas and their node descriptions.
2. Infer one or more likely nodes from the task intent and render their concrete paths.
3. Search existing files at those candidate paths, then nearby filenames, headings, and body text inside the selected base.
4. Use the strongest matching knowledge as context.
5. When managed knowledge is absent or insufficient, search the relevant project, service, or package source with scoped `rg` or `rg --files`.
6. Widen only after the scoped search fails; avoid broad repository-root scans unless the user needs exhaustive coverage.

Schema-path inference is model judgment guided by descriptions and existing files. Do not require a dedicated ranking command. Context lookup is read-only and never authorizes materialization or edits.

## Finding knowledge

- Treat the target as either a file-like path or search query.
- Search matching filenames first, then headings and body text.
- Prefer updating an existing knowledge file over creating a near-duplicate.
- Use schema descriptions to select candidate nodes and insertion policy only as a tiebreaker.
- Resolve references such as `spec 30` against existing numbered spec folders before choosing a destination.

## Path and schema rules

- Expand only the selected base root; do not expand shell syntax in user-provided targets.
- Resolve the final path after `..`, symlinks, and relative segments, then reject paths outside the base root.
- Match a file-like target to the nearest schema node.
- Render the concrete path using the selected base's `path_style`.
- Distinguish folder-based units from their sidecars. For example, a `specs/{NN}-{slug}/reports/{report}.md` report belongs to an existing spec unit.
- Materialize only the chosen node with `mem.py schema materialize --base ... --include ...`.
- Do not invent route metadata fields. Use them only when the schema template or existing file defines them.
- Treat disagreement between the expected schema path and an existing candidate as schema drift.
- Repair clear mechanical drift before writing; ask when the intended repair is ambiguous.

## Adding or updating knowledge

- Read the existing target and headings before editing.
- Preserve its stable format and organization.
- Follow the selected node's template and section shape.
- Add the smallest durable content that will remain useful.
- Include source context such as the originating command, file, log, PR, conversation, date, or rationale.
- Merge duplicate findings instead of repeating them.
- Label uncertainty; do not record speculation as fact.

After a schema-derived move or rename, verify:

- The expected file exists.
- Wrong-path siblings created by the operation are absent.
- Empty obsolete directories are removed or reported.
- Route or index metadata points to the concrete expected path.

## Protected sections

Before editing Markdown, search for `## Manual Notes` and preservation text such as `[keep this for the user to add notes. do not change between edits]`.

When present:

- Treat the section body as user-owned.
- Do not modify, reflow, move, remove, or append inside it without explicit permission.
- Put implementation, status, review, and changelog updates outside it.
- Verify the final diff leaves the section unchanged.

## Ending sections

Apply the `$specy` Required Ending Sections contract unless the selected schema specifies a different shape.

- End revised notes with `## Manual Notes`, the exact preservation marker, then `## Changelog`.
- Preserve an existing manual-notes body byte-for-byte.
- Append one changelog entry per write:

  ```text
  - YYYY-MM-DD HH:MM: description of update (agent session id - current git sha)
  ```

- Resolve the active session with `$dev.llm-session`.
- Use the owning repository's current Git SHA, or `no-git-sha` outside a worktree.

## Reads

- Search before answering.
- Read the most relevant matches.
- Interpret fields and relationships using the resolved schema.
- Summarize what the knowledge base says, not assumptions.
- Cite exact local files and lines when required.

## Deletes

Delete only when explicitly requested. Prefer targeted removal over deleting an entire file, and report the exact path changed.

## Failure states

- Missing config: exit the `$mem` workflow successfully and continue the underlying task without `$mem`. Do not ask for setup or report a blocker solely because neither the nearest ancestor `.mem.yaml` nor `$HOME/.mem.yaml` exists.
- Invalid config: report the parser error and stop.
- Missing root: report the configured path and stop.
- Missing optional base skill: report it and stop before operating in that base.
- Missing or conflicting schemas: report them and stop before reading or writing.
