---
name: todo-audit-skill
description: "Audit, fix, and analyze TODO comments across a codebase. Detects TODO:/?TODO:/!TODO: markers, classifies each by type and code scope, ranks fix difficulty 1-5, and drives an audit → fix → analyze loop."
user-invocable: true
disable-model-invocation: false
---

# TODO Audit Skill

## Purpose

Turn scattered `TODO` comments into a triaged, actionable worklist. A Python
engine finds every TODO and reports deterministic facts (file, line, type,
scope); the model interprets those facts to rank difficulty, suggest fixes,
consolidate related items, and ask clarifying questions.

## Convention

Three marker types are recognized inside real comments (never inside strings):

| Marker    | Type     | Meaning                                       | Color  |
|-----------|----------|-----------------------------------------------|--------|
| `TODO:`   | plain    | routine work                                  | orange |
| `?TODO:`  | question | needs investigation                           | blue   |
| `!TODO:`  | urgent   | imperative statement of what must be done     | red    |

Sort order is always **urgent (`!`) → question (`?`) → plain**.

## The Scanner

Get deterministic facts by running the bundled Python engine from the project
root:

```bash
todo-audit scan .            # if installed as a console script
# or, from source:
PYTHONPATH=src python3 -m todo_audit.cli scan .
```

It prints JSON: `{ root, count, todos: [{file, line, type, scope, description, color}] }`.
`scope` is one of `module`, `class`, `function`, `function-inner`. Python scope
is exact (via `ast`); JS/TS is structural (best-effort); other languages report
`module`.

## Commands

- `/todo:audit` — scan, list by severity, rank difficulty, suggest fixes, ask clarifying questions.
- `/todo:fix` — apply fixes established by an audit; route system-level fixes to `CLAUDE.md`.
- `/todo:analyze` — check code against `CLAUDE.md` requirements and propose new TODOs.

Each command's full process lives in `commands/todo/<name>.md`.

## Difficulty Scale

1 immediate fix · 2 refactor/reordering · 3 minor local rewrite ·
4 module/system-level rewrite · 5 solution requiring complete redesign.

## Routing Rule

Every suggested fix is classified **system** or **temporary**. Only **system**
fixes (typically difficulty 4–5, future-facing) are recorded in `CLAUDE.md`;
temporary fixes are never persisted there.
