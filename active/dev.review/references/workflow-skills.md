# Skill Review Workflow

Use this workflow to review `SKILL.md` files, skill directories, and bundled skill resources for correctness and context efficiency.

## Goals

- Confirm the skill will do the requested job reliably.
- Confirm the skill gives agents the non-obvious instructions, sources of truth, edge cases, and validation steps needed to complete the workflow.
- Keep always-loaded context small: the description should only support invocation, and detailed variants should live in `./references`.

## Steps

1. Resolve the real skill source.
   - Invoke `$sc` for the local skill-authoring contract.
   - Confirm the reviewed path is an editable source tree, not a runtime mirror under `~/.codex/skills`.
   - If the user gave only an installed-skill path, find the canonical source before treating the review as complete.
2. Check invocation metadata.
   - Verify frontmatter `name` matches the skill folder and request.
   - Verify `description` contains only the domain and strongest trigger cues needed before the body loads.
   - Flag descriptions that include detailed workflow steps, examples, subcommands, edge cases, or config formats that belong in the body or references.
3. Check workflow correctness.
   - Map the user's intended examples to the skill instructions and identify missing steps, source-of-truth lookups, setup, credentials, file roots, edge cases, failure handling, and exit conditions.
   - Verify the skill names required dependencies explicitly when it relies on another skill.
   - Verify commands, scripts, and generated artifacts have clear working directories, inputs, outputs, and validation.
4. Check progressive disclosure.
   - Keep `SKILL.md` focused on core routing and instructions that every invocation needs.
   - Move subcommands, long templates, provider variants, schemas, command catalogs, and examples into `./references`.
   - Prefer `./scripts` for repeated deterministic logic and `./assets` for files used in outputs.
   - Flag duplicated content between `SKILL.md` and references.
5. Check packaging and portability.
   - Require bundled file links to be relative to the `SKILL.md` directory, such as `./scripts/...`, `./references/...`, and `./assets/...`.
   - Require cross-skill references to use `$skill-name` and list the referenced
     skill in frontmatter `dependencies`; do not link directly to sibling skill
     paths.
   - Flag extra documentation files such as `README.md`, changelogs, setup guides, or quick references unless the skill explicitly consumes them.
6. Check validation evidence.
   - For changed skills, expect dependency sync when explicit skill references changed.
   - Expect `quick_validate.py` or `package_skill.py` evidence when the review is close to acceptance.
   - Distinguish "source updated" from "runtime mirror refreshed" in findings and handoff notes.

## Severity Guidance

- `blocker`: wrong source tree or runtime mirror reviewed as canonical; skill cannot accomplish the stated goal; missing required source-of-truth lookup; unsafe or non-portable command/path contract.
- `major`: overbroad or under-specified description; missing edge cases, validation, or dependencies; important workflow details buried in an unloaded or undiscoverable file; context-heavy body that should be split into references.
- `minor`: wording, naming, or structure issues that reduce clarity but do not change behavior.
- `nit`: formatting or local consistency issues.

## Output

- Lead with findings ordered by severity.
- For each finding, state the failed skill contract, why it matters for future invocations, and the smallest concrete fix.
- Include a short "Context Efficiency" note when there are no major findings but the skill can be slimmer.
- Include a short "Validation" note naming the checks run or the checks still needed.
