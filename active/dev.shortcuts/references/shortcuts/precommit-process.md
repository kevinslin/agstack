---
name: precommit-process
description: Follow before committing code
----

Instructions:

This process must be followed before committing code!

Create a to-do list with the following items then perform all of them:

1. **Confirm spec is in sync:** If work is done using a spec, review and make any updates to the spec to be sure it is current with respect to the current code.

Add any status updates to the spec to include accomplished tasks and remaining tasks, if any.

2. **Code style enforcement:**

Before code is committed all changes must be reviewed and ensure they comply with coding rules of codebase. 

3. **Code review:**

   Read all changes and ensure they follow best practices for modern TypeScript.
   Code should be clean, with brief and maintainable comments.

   You must review all outstanding changes that are not committed in the current repo.

4. **Unit testing and integration testing:**

Cover the codegen, formatting, linting, unit, and integration checks required by
the repository and accepted plan. Apply the active workflow's evidence-reuse
rules: run missing or invalidated checks, and rerun the full suite when explicitly
required. Read @docs/development.md for repository-specific test workflows.

Run repository-mandated validation commands unless higher-priority instructions
prohibit them. A phase commit alone does not require repeating still-valid checks.

Fix in-scope regressions. Classify and report other failures under the active
workflow; do not expand into unrelated repairs without authorization. Unresolved
required checks remain blockers, not waived passes.

5. **Review spec once more:**

   Make any updates to the spec based on the fixes or issues discovered during review
   and testing.

6. **Summarize and prepare a commit message:** Do NOT commit, but summarize everything
   that was done. Write a clear commit message based on this summary that you would use
   for a commit and ask the user if they want to commit this code.
