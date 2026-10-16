# Agtask

## Overview

Create one fresh, pinned Codex chat in the current project and checkout. Install
one small prompt hook with `agtask setup`; app tools own all chat state.

- [Skill router](./SKILL.md)
- [Create a task](./references/create.md)
- [Set up the hook](./references/setup.md)

The current app flow creates a setup-only chat, assigns its title and pinned
section, then sends actual work to that same chat. It keeps native model defaults
and creates no ledger, cache, lifecycle records, or worktrees. Hook output asks
the model to apply app actions; it does not apply them itself.

## Local checks

Python 3 and its standard library are sufficient:

```sh
python3 -m unittest discover -s ./tests -v
python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("./scripts/hooks.py").read_text())'
```

Tests use temporary `CODEX_HOME` directories and subprocesses. They do not create
app chats or call a network or database. These checks do not prove native app
creation, hook reload, pinning order, or remote-host behavior.
