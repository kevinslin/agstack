# Code Development Skill

A comprehensive skill for any coding task, providing best practices, security guidelines, testing strategies, and a structured development workflow.

## When This Skill Activates

This skill is automatically invoked when you're performing any coding task, including:
- Implementing new features
- Fixing bugs
- Refactoring code
- Adding or modifying tests
- Optimizing performance
- Making any source code modifications

## What This Skill Provides

### Structured Workflow
1. **Understand Before Coding** - Read and comprehend existing implementation
2. **Plan the Implementation** - Break down tasks and consider edge cases
3. **Write Quality Code** - Follow best practices and conventions
4. **Testing** - Add tests when changing behavior
5. **Review Your Work** - Catch issues before completion
6. **Iterate and Improve** - Debug and fix until tests pass

### Documentation and Deferred Work
- Create or update user-facing documentation when introducing a component.
- Keep README navigation and adjacent existing documentation accurate.
- Use `$docy` for the relevant documentation-writing guidance.
- Add concise TODOs beside temporary or deferred code, including the missing
  capability and replacement or removal condition.
- Do not describe permanent safeguards as temporary.

### Security by Default
- Comprehensive coverage of OWASP Top 10 vulnerabilities
- Input validation and sanitization patterns
- Authentication and authorization best practices
- Cryptography guidelines
- Security checklist for every code change
- See `./references/security-guidelines.md` for detailed examples

### Testing Excellence
- **Integration-first testing philosophy** - Test the full application as users would
- Unit tests used sparingly for complex logic
- Jest as the recommended framework for TypeScript/JavaScript
- Test structure patterns (AAA, Given-When-Then)
- Coverage guidelines naturally achieved through integration tests
- See `./references/testing-guidelines.md` for comprehensive guide

### Best Practices
- Code style and conventions
- Error handling patterns
- Performance considerations
- Language-specific idioms
- Common anti-patterns to avoid
- Git workflow integration

## Skill Contents

```
code/
├── SKILL.md                              # Main skill file with workflow
├── README.md                             # This file
└── references/
    ├── security-guidelines.md            # Detailed security guidance
    └── testing-guidelines.md             # Comprehensive testing guide
```

## Key Reminders

- **Security First**: Never introduce vulnerabilities (XSS, injection, etc.)
- **Test Changes**: Write integration tests first, unit tests sparingly
- **Use Jest**: For TypeScript/JavaScript projects
- **Follow Conventions**: Match existing codebase style and patterns
- **Handle Errors**: Don't let exceptions crash the system
- **Review Before Completing**: Catch issues early
- **Document Components**: Ship user-facing guides and current adjacent docs
- **Explain Deferred Work**: Mark temporary code with actionable TODOs
- **Iterate on Failures**: Don't mark tasks complete when tests fail

## Usage

This skill is designed to be automatically invoked by an agent when performing coding tasks. The skill provides:

1. **In-context guidance** - Workflow and best practices in SKILL.md
2. **Deep-dive references** - Detailed security and testing guidelines loaded as needed
3. **Language-agnostic principles** - Core concepts that apply across all languages
4. **Specific examples** - Code samples for common patterns and anti-patterns

## Benefits

- **Consistency** - Structured approach to all coding tasks
- **Quality** - Built-in best practices and review steps
- **Security** - Security considerations at every step
- **Reliability** - Testing guidance for robust code
- **Efficiency** - Proven workflows save time and reduce errors

## Version

1.0.0
