---
name: sc
description: Create, update, or optimize skills and SKILL.md content.
dependencies: []
license: Complete terms in LICENSE.txt
---

# sc

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend an agent's capabilities by providing
specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
domains or tasks—they transform a general-purpose agent into a specialized agent
equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. Specialized workflows - Multi-step procedures for specific domains
2. Tool integrations - Instructions for working with specific file formats or APIs
3. Domain expertise - Company-specific knowledge, schemas, business logic
4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks

## Skill File Location
When creating or updating a skill - ALWAYS restrict all edits to the following working directories unless overridden elsewhere:
- public: ~/code/skills/active
- private: ~/code/skills-private
- local: ./.agents/skills

NEVER directly make updates to runtime-installed skill mirrors. Edit the source tree instead.

## Git Workflow

- Work directly on the skill repository's `main` branch by default.
- NEVER create a branch, branch-backed worktree, or pull request for skill work
  unless the user explicitly requests that exception.
- Verify the current branch before editing. If it is not `main` and the user has
  not explicitly requested another branch, stop and resolve the mismatch
  without creating a branch or overwriting unrelated work.
- When the user requests a commit or push, use the existing `main` branch unless
  their instructions explicitly specify another branch.

## Usage
Always ask the user where they want the new skill to be created if they haven't already mentioned it.

When user tells you the name of a skill (eg. `dev.create-foo`), create a skill in a folder with the same name. the `SKILL.md` file within should have the frontmatter name also set to the same name.

When the user asks for a predefined skill shape, use template-based creation. Preferred phrasing:

- `$sc create {{name}} skill using {{template}} template`

When the user uses that phrasing, run `./scripts/init_skill.py <skill-name> --path <output-directory> --template <template>`.

Supported templates:

- `subcommands`: Use for skills that primarily route to multiple subcommands. Put each subcommand's full usage in `./references/{{command}}.md`. Keep the main `SKILL.md` as a router only: list each subcommand, give a one-line hint for when to lead with it, and point to the matching reference file.
- `template`: Use for skills that primarily route to multiple named templates. Put each template's full usage in `./references/{{template}}.md`. Keep the main `SKILL.md` as a router only: list each template, explain when a user invoking the skill with that template as the positional command should route there, and point to the matching reference file.

### Optimize an existing skill

When the user asks to optimize, streamline, simplify, or clean up an existing skill, read `./references/optimize.md` and apply its workflow. Treat a direct edit request as authorization for in-scope changes. Ask for clarification when the canonical source is ambiguous or when different interpretations would materially change behavior or scope.

Before editing, run a deterministic source preflight:

1. Resolve the real editable root under `~/code/skills/active`, `~/code/skills-private`, or `./.agents/skills`.
2. Confirm the skill lives in the editable source tree, not a runtime mirror or generated install location.
3. Lock the canonical edit path once and reuse it for the rest of the task so you do not re-discover mirror-vs-source rules later.
4. Inspect whether the requested change affects this skill's dependencies or any skills that depend on it; update dependency metadata, explicit skill references, and related dependency docs/scripts when needed.

### AGENTS.md Install Guardrail

When installing or documenting the `sc` skill in an `AGENTS.md`, add this line:

```markdown
- NEVER directly modify `~/.codex/skills`; ALWAYS invoke `$sc` skill when modifying skills to find the real path for skills.
```

Use this guardrail to prevent editing the runtime mirror in `~/.codex/skills` when the real editable skill lives in `skills-public`, `skills-private`, or another allowed root.

## Path Variable Conventions

When documenting path conventions in skills or `AGENTS.md`, prefer explicit semantics:

- `ROOT_DIR`: Base path for general outputs and local artifacts (for example progress files, scratch outputs, or non-doc generated files).
- `DOCS_ROOT`: Base path for documentation outputs (for example specs, design docs, flow docs, and research docs).

Do not overload `DOCS_ROOT` to mean both "where docs are written" and "all possible fallback lookup roots". If a skill needs fallback read locations, document them separately with explicit names.

## Path References

When a skill references a bundled file, write the path relative to the directory containing `SKILL.md`.

- Use `./scripts/...`, `./references/...`, and `./assets/...` for bundled resources.
- Reference another skill by name with `$<skill-name>` and add that name to frontmatter `dependencies`.
- Do not use absolute filesystem paths or repo-root-anchored skill paths for packaged skill content.
- Do not use another skill's `SKILL.md` file path as a cross-skill reference.

## Core Principles

### Concise is Key

The context window is a public good. Skills share the context window with everything else the agent needs: system prompt, conversation history, other skills' metadata, and the actual user request.

**Default assumption: the agent is already capable.** Only add context the agent doesn't already have. Challenge each piece of information: "Does the agent really need this explanation?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability:

**High freedom (text-based instructions)**: Use when multiple approaches are valid, decisions depend on context, or heuristics guide the approach.

**Medium freedom (sudocode or scripts with parameters)**: Use when a preferred pattern exists, some variation is acceptable, or configuration affects behavior.

**Low freedom (specific scripts, few parameters)**: Use when operations are fragile and error-prone, consistency is critical, or a specific sequence must be followed.

Think of the agent as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).

### Anatomy of a Skill

Every skill consists of a required SKILL.md file and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   ├── description: (required)
│   │   └── dependencies: (required list; can be empty)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation intended to be loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts, etc.)
```

#### SKILL.md (required)

Every SKILL.md consists of:

- **Frontmatter** (YAML): Contains `name`, `description`, and `dependencies` fields. `dependencies` is a list of other skill names this skill depends on.
- **Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers (if at all).

#### Bundled Resources (optional)

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `./scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by the agent for patching or environment-specific adjustments

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform the agent's process and reasoning.

- **When to include**: For documentation that the agent should reference while working
- **Examples**: `./references/finance.md` for financial schemas, `./references/mnda.md` for company NDA template, `./references/policies.md` for company policies, `./references/api_docs.md` for API specifications
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when the agent determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output the agent produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `./assets/logo.png` for brand assets, `./assets/slides.pptx` for PowerPoint templates, `./assets/frontend-template/` for HTML/React boilerplate, `./assets/font.ttf` for typography
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents that get copied or modified
- **Benefits**: Separates output resources from documentation, enables the agent to use files without loading them into context

#### What to Not Include in a Skill

A skill should only contain essential files that directly support its functionality. Do NOT create extraneous documentation or auxiliary files, including:

- README.md
- INSTALLATION_GUIDE.md
- QUICK_REFERENCE.md
- CHANGELOG.md
- etc.

The skill should only contain the information needed for an AI agent to do the job at hand. It should not contain auxilary context about the process that went into creating it, setup and testing procedures, user-facing documentation, etc. Creating additional documentation files just adds clutter and confusion.

### Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

1. **Metadata (name + description)** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<5k words)
3. **Bundled resources** - As needed by the agent (Unlimited because scripts can be executed without reading into context window)

#### Progressive Disclosure Patterns

Keep SKILL.md body to the essentials and under 500 lines to minimize context bloat. Split content into separate files when approaching this limit. When splitting out content into other files, it is very important to reference them from SKILL.md and describe clearly when to read them, to ensure the reader of the skill knows they exist and when to use them.

**Key principle:** When a skill supports multiple variations, frameworks, or options, keep only the core workflow and selection guidance in SKILL.md. Move variant-specific details (patterns, examples, configuration) into separate reference files.

**Pattern 1: High-level guide with references**

```markdown
# PDF Processing

## Quick start

Extract text with pdfplumber:
[code example]

## Advanced features

- **Form filling**: See [FORMS.md](FORMS.md) for complete guide
- **API reference**: See [REFERENCE.md](REFERENCE.md) for all methods
- **Examples**: See [EXAMPLES.md](EXAMPLES.md) for common patterns
```

The agent loads FORMS.md, REFERENCE.md, or EXAMPLES.md only when needed.

**Pattern 2: Domain-specific organization**

For Skills with multiple domains, organize content by domain to avoid loading irrelevant context:

```
bigquery-skill/
├── SKILL.md (overview and navigation)
└── reference/
    ├── finance.md (revenue, billing metrics)
    ├── sales.md (opportunities, pipeline)
    ├── product.md (API usage, features)
    └── marketing.md (campaigns, attribution)
```

When a user asks about sales metrics, the agent only reads sales.md.

Similarly, for skills supporting multiple frameworks or variants, organize by variant:

```
cloud-deploy/
├── SKILL.md (workflow + provider selection)
└── references/
    ├── aws.md (AWS deployment patterns)
    ├── gcp.md (GCP deployment patterns)
    └── azure.md (Azure deployment patterns)
```

When the user chooses AWS, the agent only reads aws.md.

**Pattern 3: Conditional details**

Show basic content, link to advanced content:

```markdown
# DOCX Processing

## Creating documents

Use docx-js for new documents. See [DOCX-JS.md](DOCX-JS.md).

## Editing documents

For simple edits, modify the XML directly.

**For tracked changes**: See [REDLINING.md](REDLINING.md)
**For OOXML details**: See [OOXML.md](OOXML.md)
```

The agent reads REDLINING.md or OOXML.md only when the user needs those features.

**Important guidelines:**

- **Avoid deeply nested references** - Keep references one level deep from SKILL.md. All reference files should link directly from SKILL.md.
- **Structure longer reference files** - For files longer than 100 lines, include a table of contents at the top so the agent can see the full scope when previewing.

## Skill Creation Process

Skill creation involves these steps:

1. Understand the skill with concrete examples
2. Plan reusable skill contents (scripts, references, assets)
3. Initialize the skill (run init_skill.py)
4. Edit the skill (implement resources and write SKILL.md)
5. Package the skill (run package_skill.py)
6. Iterate based on real usage

Follow these steps in order, skipping only if there is a clear reason why they are not applicable.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood. It remains valuable even when working with an existing skill.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "I can imagine users asking for things like 'Remove the red-eye from this image' or 'Rotate this image'. Are there other ways you imagine this skill being used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message. Start with the most important questions and follow up as needed for better effectiveness.

Conclude this step when there is a clear sense of the functionality the skill should support.

### Step 2: Planning the Reusable Skill Contents

To turn concrete examples into an effective skill, analyze each example by:

1. Considering how to execute on the example from scratch
2. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly

Example: When building a `pdf-editor` skill to handle queries like "Help me rotate this PDF," the analysis shows:

1. Rotating a PDF requires re-writing the same code each time
2. A `./scripts/rotate_pdf.py` script would be helpful to store in the skill

Example: When designing a `frontend-webapp-builder` skill for queries like "Build me a todo app" or "Build me a dashboard to track my steps," the analysis shows:

1. Writing a frontend webapp requires the same boilerplate HTML/React each time
2. An `./assets/hello-world/` template containing the boilerplate HTML/React project files would be helpful to store in the skill

Example: When building a `big-query` skill to handle queries like "How many users have logged in today?" the analysis shows:

1. Querying BigQuery requires re-discovering the table schemas and relationships each time
2. A `./references/schema.md` file documenting the table schemas would be helpful to store in the skill

To establish the skill's contents, analyze each concrete example to create a list of the reusable resources to include: scripts, references, and assets.

### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

When creating a new skill from scratch, always run the `init_skill.py` script. The script conveniently generates a new template skill directory that automatically includes everything a skill requires, making the skill creation process much more efficient and reliable.

Usage:

```bash
./scripts/init_skill.py <skill-name> --path <output-directory>
```

Template-based usage:

```bash
./scripts/init_skill.py <skill-name> --path <output-directory> --template <template>
```

The script:

- Creates the skill directory at the specified path
- Generates a template-specific `SKILL.md` scaffold with proper frontmatter and TODO placeholders
- Creates only the resource directories needed by the selected template
- Adds template-specific example files that can be customized or deleted

Current templates:

- `subcommands`: creates a router-style `SKILL.md` plus per-command references in `./references/{{command}}.md`
- `template`: creates a router-style `SKILL.md` plus per-template references in `./references/{{template}}.md`

After initialization, customize or remove the generated SKILL.md and example files as needed.

### Step 4: Edit the Skill

When editing the (newly-generated or existing) skill, remember that the skill is being created for another agent instance to use. Include information that would be beneficial and non-obvious to the agent. Consider what procedural knowledge, domain-specific details, or reusable assets would help another agent instance execute these tasks more effectively.

#### Learn Proven Design Patterns

Consult these helpful guides based on your skill's needs:

- **Multi-step processes**: See `./references/workflows.md` for sequential workflows and conditional logic
- **Specific output formats or quality standards**: See `./references/output-patterns.md` for template and example patterns

These files contain established best practices for effective skill design.

#### Updating Documentation Workflow Instructions

When a user asks to update a documentation workflow such as flow docs, edit the owning skill's source `./references/.../workflow.md`, `./references/.../template.md`, and any validator/tests that enforce the workflow. Keep the main `SKILL.md` as a lean router, and do not copy detailed workflow policy into runtime-installed skill mirrors.

#### Start with Reusable Skill Contents

To begin implementation, start with the reusable resources identified above: `scripts/`, `references/`, and `assets/` files. Note that this step may require user input. For example, when implementing a `brand-guidelines` skill, the user may need to provide brand assets or templates to store in `assets/`, or documentation to store in `references/`.

Added scripts must be tested by actually running them to ensure there are no bugs and that the output matches what is expected. If there are many similar scripts, only a representative sample needs to be tested to ensure confidence that they all work while balancing time to completion.

Any example files and directories not needed for the skill should be deleted. The initialization script creates only the files needed by the selected template, but the generated placeholders should still be trimmed to the actual skill.

#### Editing SKILL.md

**Writing Guidelines:** Always use imperative/infinitive form.

##### Dependency Impact Check

Before editing, inspect dependency impact:

- If the change adds or removes a `$<skill-name>` reference, update frontmatter `dependencies` to match.
- If the change alters a contract used by dependent skills, search for affected skill references and update those dependent skills when they live in an allowed editable root.
- If dependency-related scripts, references, or packaging behavior are affected, inspect and update those bundled resources in the same change.
- After edits that affect dependencies, run `./scripts/sync_dependencies.py <path/to/skill-folder>` and report any dependency/body-reference files that changed.

##### Frontmatter

Write the YAML frontmatter with `name`, `description`, and `dependencies`:

- `name`: The skill name
- `description`: Keep this short. Include only the information needed for the model to decide whether to trigger the skill.
  - Prefer one short sentence with the skill's domain and the strongest trigger.
  - Put workflow details, configuration formats, file types, edge cases, and examples in the body, not the description.
  - Bad: `Add, find, read, update, or delete knowledge in configured knowledge kernels using configured base skills and kernel schemas, including persistent routing and configuration details.`
  - Good: `Manage user-defined knowledge kernels. Use when directly invoked.`
- `dependencies`: YAML list of skill names this skill depends on (example: `dependencies: [specy, dev.llm-session]`).
  - Use `dependencies: []` when there are no dependencies.
- Reference other skills in the body by name using `$<skill-name>`.
- Automatically synchronize named skill references into frontmatter dependencies with:
    - `./scripts/sync_dependencies.py <path/to/skill-folder>`
- Dependency synchronization adds only sibling or runtime-installed skills. It preserves explicitly declared dependencies and warns about unresolved `$<token>` references without adding them.

Do not include unapproved fields in YAML frontmatter (approved: `name`, `description`, `dependencies`, and repository-specific optional fields such as `version`, `license`, `allowed-tools`, `metadata`).

##### Body

Write instructions for using the skill and its bundled resources.

### Step 5: Packaging a Skill

Once development of the skill is complete, it must be packaged into a distributable .skill file that gets shared with the user. The packaging process automatically validates the skill first to ensure it meets all requirements:

```bash
./scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory specification:

```bash
./scripts/package_skill.py <path/to/skill-folder> ./dist
```

The packaging script will:

1. **Sync + Validate** the skill automatically, checking:

   - dependency metadata is synchronized from `$<skill-name>` references in body content
   - YAML frontmatter format and required fields
   - Skill naming conventions and directory structure
   - Description completeness and quality
   - File organization and resource references

2. **Package** the skill if validation passes, creating a .skill file named after the skill (e.g., `my-skill.skill`) that includes all files and maintains the proper directory structure for distribution. The .skill file is a zip file with a .skill extension.

If validation fails, the script will report the errors and exit without creating a package. Fix any validation errors and run the packaging command again.

### Step 6: Iterate

After testing the skill, users may request improvements. Often this happens right after using the skill, with fresh context of how the skill performed.

**Iteration workflow:**

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Identify how SKILL.md or bundled resources should be updated
4. Implement changes and test again

## Updating a Skill

When a user asks "update this skill to do X":

- Derive the target skill name or path from the request or prior context.
- Resolve the on-disk path using only the allowed roots in **Skill File Location**.
  - public: `~/code/skills-public/{drafts|active}/<skill-name>`
  - private: `~/code/skills-private/<skill-name>`
  - local: `./skills/<skill-name>`
- If the location is ambiguous or multiple matches exist, ask which root (and drafts vs active) to use before editing.
- Do not edit skills outside those roots.

When changing a skill name:

- Run:
  - `./scripts/rename_skill.py <workspace-root> <old-skill-name> <new-skill-name>`
- This updates:
  - skill directory name (when present),
  - frontmatter `name`,
  - frontmatter `dependencies`,
  - skill body references.
- If the script reports updated files, notify the user explicitly that dependency/body references were changed and list the files.
