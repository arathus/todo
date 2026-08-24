---
name: todo-audit-skill
description: "Audit, fix, and analyze TODO comments across a codebase. Detects TODO:/?TODO:/!TODO: plus FIXME/HACK/XXX markers, classifies each by type and code scope, names the enclosing symbol, ranks fix difficulty 1-5, and drives an audit → fix → analyze loop."
user-invocable: true
disable-model-invocation: false
---

# TODO Audit Skill

## Purpose

Turn scattered `TODO` comments into a triaged, actionable worklist. A Python
engine finds every TODO and reports deterministic facts (file, line, type,
scope, enclosing symbol); the model interprets those facts to rank difficulty,
suggest fixes, consolidate related items, and ask clarifying questions.

## Convention

Three marker types are recognized inside real comments (never inside strings):

| Marker    | Type     | Meaning                                       | Color  |
|-----------|----------|-----------------------------------------------|--------|
| `TODO:`   | plain    | routine work                                  | orange |
| `?TODO:`  | question | needs investigation                           | blue   |
| `!TODO:`  | urgent   | imperative statement of what must be done     | red    |

Sort order is always **urgent (`!`) → question (`?`) → plain**.

Three further keywords are recognized and carry a default type, which an
explicit sigil always overrides (`?FIXME:` is a question):

| Keyword  | Default type | Rationale                        |
|----------|--------------|----------------------------------|
| `FIXME:` | urgent       | asserts something is broken now  |
| `XXX:`   | urgent       | conventional danger marker       |
| `HACK:`  | plain        | a known workaround; routine debt |

`TODO(alice):` and `TODO(#412):` are recognized too; the parenthesised owner is
reported separately in `assignee`. An indented comment line directly below a
marker continues its description.

## The Scanner

Run the engine from the project root being audited. The engine ships inside the
skill, so the fallback must point `PYTHONPATH` at the skill's own `src/`, not at
the audited project:

```bash
todo-audit scan . || {
  [ $? -eq 127 ] && PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/todo-audit-skill}/src" \
    python3 -m todo_audit.cli scan .
}
```

Branch on the exit code; do not chain blindly with `||`:

| Exit | Meaning |
|------|---------|
| `0`  | success — JSON on stdout |
| `2`  | refused — the path does not exist, or it is third-party code. Read stderr and repoint. |
| `127`| the console script is absent — use the `PYTHONPATH` branch |

**Never discard stderr.** It carries two diagnostics the user needs: a `note:`
that `.gitignore` could not be applied (so ignored files may appear in the
results), and the `error:` explaining a refusal.

### Payload

```jsonc
{
  "root": ".", "count": 2,
  "summary":    { "by_type": {…}, "by_scope": {…}, "by_marker": {…}, "files": 2 },
  "vocabulary": { "difficulty": {…}, "fix_kinds": [...], "severity_order": [...] },
  "todos": [ { "file", "line", "type", "scope", "description",
               "marker", "symbol", "assignee", "color", "id" } ]
}
```

- Read `summary` before the array, and report the totals first.
- Use `vocabulary` verbatim for the difficulty labels and fix kinds — it is the
  single source of truth; do not restate the scale from memory.
- `symbol` names the enclosing function or class (dotted, e.g.
  `PaymentService.refund`). Prefer it over opening the file.
- `id` is a stable content hash that ignores the line number, so it survives
  edits above the TODO. Deduplicate on it.
- `scope` is one of `module`, `class`, `function`, `function-inner`. Python scope
  is exact (via `ast`); JS/TS is structural (best-effort); other languages report
  `module`.

### What is scanned

**Only code the user wrote.** Dependency trees are pruned in every ecosystem
(`node_modules`, `vendor`, `Pods`, `site-packages`, `third_party`, …), virtual
environments are detected by their `pyvenv.cfg` regardless of directory name,
build output and caches are skipped, and generated files (`*.min.js`,
`*_pb2.py`, …) are excluded. `.gitignore` is honored at every directory level,
and files over 5 MB are skipped.

`.gitignore` support needs the optional `pathspec` package. If it is missing for
the interpreter running the scan, the engine says so on stderr and falls back to
the built-in denylist. Surface that note; installing it is
`python3 -m pip install pathspec`.

## Commands

- `/todo:audit` — scan, list by severity, rank difficulty, suggest fixes, ask
  clarifying questions. Read-only.
- `/todo:fix` — apply fixes **after explicit user approval**, route system-level
  fixes to `CLAUDE.md`, then run the project's checks and report the result.
- `/todo:analyze` — check code against the requirements declared in every
  `CLAUDE.md` location and propose new TODOs as a diff, for approval.

Each command's full process lives in `commands/<name>.md`.

## Difficulty Scale

Authoritative values come from `vocabulary.difficulty` in the scan payload:
1 immediate fix · 2 refactor / reordering · 3 minor local rewrite ·
4 module or system-level rewrite · 5 solution requiring complete redesign.

## Routing Rule

Every suggested fix is classified **system** or **temporary**. Only **system**
fixes (typically difficulty 4–5, future-facing) are recorded in `CLAUDE.md`, and
their TODO comment stays in the code pointing at that entry; temporary fixes are
applied in code and never persisted there.
