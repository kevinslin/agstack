---
name: dev.code
description: Implement, fix, refactor, or otherwise modify source code.
dependencies:
- docy
version: 1.0.0
---

# Code Development Skill

This skill provides a structured approach to coding tasks with emphasis on quality, security, and maintainability.

## When to Use This Skill

Use this skill for any coding task including:
- Implementing new features or functionality
- Fixing bugs or issues
- Refactoring existing code
- Optimizing performance
- Adding or modifying tests
- Making any changes to source code

## Core Development Workflow

### 1. Understand Before Coding

Before making changes:
- Read relevant existing code to understand current implementation
- Identify the scope of changes needed
- Ground requirements and invariants in the user's latest explicit decisions,
  current authoritative contracts, and actual enforcement boundaries
- Consider edge cases and potential side effects
- Check for existing patterns and conventions in the codebase
- Choose the smallest complete implementation; do not invent requirements,
  compatibility layers, configuration knobs, or speculative abstractions

### 2. Plan the Implementation

For non-trivial tasks:
- Use TodoWrite to break down the work into clear steps
- Identify files that need to be modified
- Consider the order of operations (e.g., tests before implementation, or vice versa)
- Plan for both happy path and error handling
- Identify every test or end-to-end outcome the user explicitly requested and
  the real runtime, credentials, or infrastructure needed to verify it
- Identify new components that need user-facing documentation and temporary
  implementation paths that need an explicit removal condition

### 3. Write Quality Code

Follow these principles:

**Code Style & Conventions:**
- Follow existing code style and patterns in the codebase
- Use spaces not tabs (per user configuration)
- Choose descriptive variable and function names
- Keep functions focused and single-purpose
- Add comments for complex logic, but prefer self-documenting code
- Reuse existing architecture and one canonical source of truth; remove
  unnecessary helpers, state machinery, duplicate configuration, and defenses
  not required by a real current contract

**Documentation and Deferred Work:**
- When introducing a component, load `$docy` guidance and add or update its
  user-facing guide in the same change. Cover its purpose, setup, configuration,
  supported boundaries, verification, and troubleshooting.
- Update relevant README links, navigation, and adjacent documents that would
  otherwise describe outdated behavior.
- Keep active specifications and user-facing documentation synchronized with
  implemented behavior, approved limitations, and remaining verification gaps.
- Mark temporary placeholders, compatibility drains, feature filters, or
  deferred behavior with a nearby concise `TODO` naming the missing capability,
  responsible milestone or owner, and replacement or removal condition.
- Explicitly mark temporary authentication, credential, transport, or network
  exceptions beside their implementation and explain their replacement path.
- Keep permanent security boundaries and intentional architecture free of
  misleading temporary markers.

**Security Considerations:**
- NEVER introduce security vulnerabilities
- Watch for: command injection, XSS, SQL injection, path traversal, insecure deserialization
- Validate and sanitize all user inputs
- Use parameterized queries for database operations
- Avoid hardcoding secrets or credentials
- Use secure defaults and principle of least privilege
- For detailed security guidance, consult `./references/security-guidelines.md`

**Error Handling:**
- Handle errors gracefully with appropriate error messages
- Avoid exposing sensitive information in error messages
- Clean up resources properly (close files, connections, etc.)
- Consider failure modes and recovery strategies

**Performance:**
- Avoid unnecessary computations or database queries
- Consider time and space complexity for data structures and algorithms
- Use caching appropriately
- Profile before optimizing (don't prematurely optimize)

### 4. Testing

**Prefer integration tests over unit tests.** Integration tests:
- Test the full application as users would interact with it
- Catch more bugs (import issues, config problems, integration bugs)
- Are easier to maintain during refactoring
- Provide confidence that the actual user experience works

When changing program behavior:
- Add tests (per user configuration)
- **Write integration tests first** - test the full application/CLI
- Run the actual application process, don't import functions directly
- Write tests that cover both happy path and edge cases
- Ensure existing tests still pass
- Add unit tests sparingly - only for complex logic that needs isolation
- Test error handling and boundary conditions
- Use the repository's existing test runner and conventions; do not introduce
  Jest, snapshots, dependencies, or snapshot updates unless the repository and
  requested behavior actually require them
- Exercise supported routes, realistic ownership and persisted state, real
  authorization, and observable outcomes at their authoritative boundary
- Reject tests that assert behavior invented by their own mocks, monkeypatches,
  fixtures, adapters, nonexistent endpoints, or impossible application states
- Add concise comments before non-obvious integration setup and assertions to
  explain the scenario and the business or security invariant being verified
- Distinguish real runtime or infrastructure execution from rendering-only
  checks, substitutes, and skipped cases; report unavailable prerequisites
  honestly instead of presenting a substitute as equivalent proof
- Run every test the user explicitly requested. If any requested test fails,
  skips, or cannot run, report that exact acceptance criterion as unverified
  and do not claim the requested outcome is complete

Test-driven development approach:
1. Write failing integration test first (recommended)
2. Implement the minimal code to make tests pass
3. Refactor while keeping tests green
4. Add unit tests only if needed for complex logic

For detailed testing guidance, consult `./references/testing-guidelines.md`

### 5. Review Your Work

Before marking a task complete:
- Re-read the changes you made
- Check for introduced bugs or regressions
- Verify security considerations are addressed
- Ensure tests pass
- Confirm each user-requested test actually ran and passed at the requested
  boundary; name any remaining infrastructure or acceptance-proof blocker
- Verify new component documentation, its links and examples, and explanations
  for every intentionally temporary implementation path
- Look for opportunities to simplify
- Remove debug code, console.logs, or temporary changes

### 6. Iterate and Improve

If errors or issues arise:
- Don't mark tasks as complete if there are failures
- Debug systematically (check error messages, add logging, isolate the issue)
- Fix the root cause, not just symptoms
- Verify the fix works with tests

## Common Patterns

### When Editing Files
- Always use Read before Edit or Write
- Preserve exact indentation when using Edit tool
- Use Edit for targeted changes, Write for new files or complete rewrites

### When Searching Code
- Use Grep for content search
- Use Glob for finding files by pattern
- Use Task tool with Explore agent for open-ended exploration

### When Working with Git
- Check git status before committing
- Write clear, concise commit messages
- Don't commit secrets, credentials, or sensitive data
- Follow the repository's commit message conventions

## Anti-Patterns to Avoid

- **Don't** write code without reading existing implementation
- **Don't** mark tasks complete when tests are failing
- **Don't** skip error handling or edge cases
- **Don't** introduce security vulnerabilities
- **Don't** hardcode values that should be configurable
- **Don't** duplicate code instead of extracting common functionality
- **Don't** leave commented-out code or debug statements
- **Don't** make changes without understanding the full impact

## Language-Specific Considerations

When working in different languages, adapt to their idioms and best practices:

**JavaScript/TypeScript:**
- Use const/let, never var
- Prefer async/await over raw promises
- Handle promise rejections
- Use TypeScript types effectively
- Use the repository's existing test framework and scripts
- Write integration tests that run the actual CLI/application process

**Python:**
- Follow PEP 8 style guidelines
- Use type hints for better code clarity
- Properly handle exceptions with try/except
- Use context managers (with statements) for resources

**Go:**
- Handle errors explicitly (don't ignore them)
- Use defer for cleanup
- Follow Go conventions (e.g., early returns)

**Rust:**
- Handle Result and Option types properly
- Use borrowing and ownership correctly
- Leverage the type system for safety

**Java:**
- Use appropriate exception handling
- Follow naming conventions (camelCase for methods/variables, PascalCase for classes)
- Properly close resources (use try-with-resources)

## Best Practices Summary

1. **Read first, code second** - Understand before changing
2. **Security by default** - Never introduce vulnerabilities
3. **Test your changes** - Write integration tests first, unit tests sparingly
4. **Follow conventions** - Match the existing codebase style
5. **Handle errors properly** - Don't let exceptions crash the system
6. **Review before submitting** - Catch issues early
7. **Iterate on feedback** - Fix problems until tests pass

For more detailed information on specific topics:
- Security best practices: `./references/security-guidelines.md`
- Testing strategies: `./references/testing-guidelines.md`
