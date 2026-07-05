<p align="center">
  <img src="docs/logo.png" alt="todo" width="440">
</p>

<p align="center">
  <em>Turn scattered <code>TODO</code> comments into a triaged, actionable worklist — a Claude Code skill backed by a dependency-free Python engine.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude%20Code-skill-8A2BE2?logo=anthropic&logoColor=white" alt="Claude Code skill">
  <img src="https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/runtime%20deps-0-success" alt="Zero runtime dependencies">
  <img src="https://img.shields.io/badge/coverage-91%25-brightgreen" alt="Coverage 91%">
  <img src="https://img.shields.io/badge/tests-25%20passing-brightgreen" alt="25 tests passing">
  <img src="https://img.shields.io/badge/types-mypy%20strict-2A6DB2" alt="mypy strict">
  <img src="https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black" alt="Ruff">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
</p>

<p align="center">
  <img src="docs/demo.gif" alt="todo-audit-skill scanning a sample module" width="820">
</p>

---

## 📋 Overview

`todo-audit-skill` gives Claude Code a disciplined way to manage the `TODO`
comments that accumulate in any real codebase. A deterministic Python engine
**finds** every TODO and reports hard facts — file, line, marker type, and code
scope — while the model **interprets** those facts to rank difficulty, suggest
fixes, consolidate related items, and ask clarifying questions.

The split is deliberate: parsing is testable and cheap, judgment needs the LLM.
Neither does the other's job.

## 🏷️ The convention

Three marker types are recognized **inside real comments** — never inside string
literals:

| Marker    | Type       | Meaning                                     | Color  |
| --------- | ---------- | ------------------------------------------- | ------ |
| `TODO:`   | `plain`    | routine work                                | 🟠 orange |
| `?TODO:`  | `question` | needs investigation before acting           | 🔵 blue   |
| `!TODO:`  | `urgent`   | imperative statement of what must be done   | 🔴 red    |

Everything sorts in one fixed order: **`!` → `?` → plain**.

## ⚡ Commands

| Command         | What it does |
| --------------- | ------------ |
| `/todo:audit`   | Scans the codebase, lists TODOs by severity, ranks each on a 1–5 difficulty scale, suggests a fix from surrounding code context, consolidates related items, and asks clarifying questions when context is thin. Read-only. |
| `/todo:fix`     | Applies the fixes established by an audit. System-level fixes are routed into a managed section of `CLAUDE.md` (deduplicated across runs); temporary fixes are never persisted. |
| `/todo:analyze` | Checks the code against the requirements declared in `CLAUDE.md` and proposes new TODOs where it diverges — presented as a diff for your approval before anything is written. |

### 📊 Difficulty scale

`1` immediate fix · `2` refactor / reordering · `3` minor local rewrite ·
`4` module or system-level rewrite · `5` solution requiring complete redesign.

## 🎯 How scope resolution works

Each TODO is tagged with the tightest structure it lives in:
`module` · `class` · `function` · `function-inner`.

| Language          | Scope accuracy | Engine |
| ----------------- | -------------- | ------ |
| Python            | **Exact**      | stdlib `ast` |
| JavaScript / TypeScript | Best-effort | structural brace-stack parser |
| C-family, Go, Rust, Java, … | Best-effort | structural brace-stack parser |
| Ruby, shell, YAML, TOML | `module` only | comment detection only |

> Tree-sitter is the natural future upgrade for exact multi-language scope.

## 🔍 The scanner

The engine is usable on its own and emits plain JSON:

```bash
todo-audit scan .                                  # installed console script
PYTHONPATH=src python3 -m todo_audit.cli scan .    # from source
```

```jsonc
{
  "root": ".",
  "count": 2,
  "todos": [
    { "file": "app.py", "line": 12, "type": "urgent",   "scope": "function-inner", "description": "handle empty payload", "color": "red" },
    { "file": "app.py", "line": 40, "type": "question", "scope": "class",          "description": "should this be cached?", "color": "blue" }
  ]
}
```

## 📦 Installation

### Via a Node package manager

| Manager | Command |
| ------- | ------- |
| npm     | `npm install -g todo-audit-skill` |
| pnpm    | `pnpm add -g todo-audit-skill` |
| yarn    | `yarn global add todo-audit-skill` |
| bun     | `bun add -g todo-audit-skill` |

A `postinstall` hook copies the skill into `~/.claude/skills/todo-audit-skill/`.
If install scripts are disabled (`--ignore-scripts`), run the installer manually:

```bash
npx todo-audit-skill-install    # or: node ./bin/installer.js
```

### 🔌 As a native Claude Code plugin

```bash
/plugin marketplace add your-username/todo-audit-skill
/plugin install todo-audit-skill@your-username
```

## 💡 Best used for

- **Pre-release triage** — see every outstanding `!TODO:` ranked by severity before you cut a tag.
- **Onboarding a legacy codebase** — get an instant map of where the debt lives and how deep each item runs.
- **Enforcing project conventions** — `/todo:analyze` turns your `CLAUDE.md` requirements into concrete, located TODOs.
- **Debt that outlives a sprint** — system-level items are promoted to `CLAUDE.md` so they don't vanish into a diff.
- **Keeping questions visible** — `?TODO:` markers surface open design decisions instead of burying them in code.

## 🛠️ Development

All tasks run through [`poe`](https://poethepoet.natn.io/) on top of
[`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev --extra gitignore
uv run poe lint          # ruff check --fix, ruff format, mypy
uv run poe lint-check    # non-mutating variant (used in CI)
uv run poe test          # pytest with branch coverage (fails under 85%)
```

Quality bar: **ruff** (lint + format), **mypy `--strict`**, and **pytest** with
branch coverage gated at 85%. The scanner itself carries **zero runtime
dependencies** (`pathspec` is an optional extra for richer `.gitignore` support).

## 📄 License & author

Licensed under [MIT](./LICENSE) · created by [arathus](https://www.linkedin.com/in/akosjakub-710583112/)
