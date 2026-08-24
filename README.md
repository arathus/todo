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
  <img src="https://img.shields.io/badge/coverage-gated%20%E2%89%A585%25-brightgreen" alt="Coverage gated at 85%">
  <img src="https://img.shields.io/badge/tests-passing-brightgreen" alt="Tests passing">
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

The sigil may sit on **either side** of the keyword: `TODO!:` reads exactly like
`!TODO:`, and `TODO?:` like `?TODO:`. Both spellings occur in the wild, so both
are accepted for every keyword. If both positions are used and disagree, the
leading one decides.

Three widespread keywords are recognized alongside `TODO`, each with a default
type that an explicit sigil overrides — `?FIXME:` is a question:

| Keyword  | Default type | Why                                     |
| -------- | ------------ | --------------------------------------- |
| `FIXME:` | `urgent`     | asserts something is broken right now   |
| `XXX:`   | `urgent`     | conventional danger marker              |
| `HACK:`  | `plain`      | a known workaround; routine debt        |

Every record reports the keyword that produced it in a `marker` field, so
`FIXME` never silently becomes an anonymous urgent TODO. Detection is
word-anchored: `NOTODO:` and `METODO:` are not markers.

The `TODO(owner):` convention is supported — `TODO(alice):` and `TODO(#412):`
both parse, and the owner is reported separately in `assignee` rather than being
buried in the description.

### Wrapped descriptions

A description spread over several comment lines is read as **one** description,
whether or not the continuation is indented:

```python
# !TODO(alice): rework the refund path
# the gateway returns 202 for partial refunds
```

The rule is *own-line comments*, not indentation. Scanning stops at the first
line that is a blank line, real code, another marker, or a tool directive or
licence header (`# noqa`, `# type:`, `Copyright`, `SPDX-`, …) — and at five
lines, so a stray comment block below a TODO cannot be swallowed whole.

Two consequences worth knowing:

- A marker **trailing a statement** owns nothing below it, and a comment
  trailing a later statement is never absorbed — `x = 1  # TODO: fix` followed by
  `y = 2  # note about y` stays two separate remarks.
- Inside a single `/* … */` the lines are one comment by definition, so they join
  even when the block opens after code. A **closed** block does not absorb the
  next one.

## ⚡ Commands

| Command         | What it does |
| --------------- | ------------ |
| `/todo:audit`   | Scans the codebase, lists TODOs by severity, consolidates related items, and ranks each on a 1–5 difficulty scale. Reports a **table** for scanning (location, symbol, difficulty, kind, one-line summary) plus a **detail block per task** for deciding — the concrete change, why the code argues for it, what it risks, and how to verify. Asks clarifying questions rather than guessing. Read-only, enforced via `allowed-tools`. |
| `/todo:fix`     | Applies fixes **after you approve them item by item**, then runs the project's checks and reports the real result. System-level fixes are routed into a managed section of `CLAUDE.md`, deduplicated on the stable `id`; their TODO comment stays in the code pointing at that entry. Temporary fixes are never persisted. |
| `/todo:analyze` | Checks the code against the requirements declared in **every** `CLAUDE.md` location Claude Code itself reads — `./CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `.claude/rules/*.md`, nested files — and proposes new TODOs as a diff for your approval before anything is written. |

Both writing commands gate on explicit approval. An audit only ever *proposes*.

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

The brace-stack parser reads `function` / `func` / `fn` declarations, `class`
bodies, arrow functions, and method headers (including `-> T` and `: T` return
types). Control-flow headers such as `if (…)` and `catch (…)` look identical to a
call but open a plain block, so they are classified as one — a TODO inside a
top-level `if` is `module`, not `function-inner`.

> Tree-sitter is the natural future upgrade for exact multi-language scope.

## 🔍 The scanner

The engine is usable on its own and emits plain JSON:

```bash
todo-audit scan .                                  # installed console script
PYTHONPATH=src python3 -m todo_audit.cli scan .    # from a checkout
# from the installed skill (what the commands use):
PYTHONPATH="$HOME/.claude/skills/todo-audit-skill/src" python3 -m todo_audit.cli scan .
```

```jsonc
{
  "root": ".",
  "count": 2,
  // read this first: prioritize without walking the whole array
  "summary": { "by_type": { "urgent": 1, "question": 1, "plain": 0 },
               "by_scope": { "function-inner": 1, "class": 1 },
               "by_marker": { "FIXME": 1, "TODO": 1 }, "files": 1 },
  // the authoritative grading vocabulary, so prose copies cannot drift
  "vocabulary": { "difficulty": { "1": "immediate fix", "5": "solution requiring complete redesign" },
                  "fix_kinds": ["system", "temporary"],
                  "severity_order": ["urgent", "question", "plain"] },
  "todos": [
    { "file": "app.py", "line": 12, "type": "urgent", "scope": "function-inner", "symbol": "Checkout.submit",
      "description": "handle empty payload", "marker": "FIXME", "assignee": "alice", "color": "red", "id": "9f2c1ab40e77" },
    { "file": "app.py", "line": 40, "type": "question", "scope": "class", "symbol": "Checkout",
      "description": "should this be cached?", "marker": "TODO", "assignee": null, "color": "blue", "id": "3d81e0c5b214" }
  ]
}
```

Two fields exist specifically so the model can work from the payload instead of
re-reading the codebase:

- **`symbol`** names the enclosing function or class (dotted, e.g.
  `Checkout.submit`). Without it, two identically worded TODOs in different
  methods are indistinguishable and every one costs a file read.
- **`id`** is a stable content hash that deliberately **excludes the line
  number**, so editing the lines above a TODO does not make it look new. It
  includes the symbol, so the same wording in two methods stays distinct. This is
  what makes `/todo:fix`'s managed `CLAUDE.md` section idempotent across runs.

### Exit codes

| Exit | Meaning |
| ---- | ------- |
| `0`  | success — JSON on stdout |
| `2`  | refused — the path does not exist, or it is third-party code (reason on stderr) |

Diagnostics go to stderr and the payload to stdout, so **never discard stderr**:
that is where an unenforceable `.gitignore` and a refusal explain themselves.

### Traversal rules

- `.gitignore` is honored at **every** directory level, closest file winning —
  the same precedence git applies. Needs the optional `pathspec` extra; without
  it only the built-in denylist applies, and the scanner says so on stderr
  rather than quietly reporting TODOs from ignored directories.
- **Only code the user wrote is audited.** Third-party trees are pruned
  unconditionally, across ecosystems: `node_modules`, `vendor`,
  `bower_components`, `Pods`, `Carthage`, `third_party`, `site-packages`,
  `.tox`, `.yarn`, `.m2`, `.gradle`, `.cargo`, `.terraform`, `*.egg-info`. A
  Python virtual environment is detected by its `pyvenv.cfg`, so it is pruned
  whatever it is named — `env/` and `myenv/` as surely as `.venv/`.
  Pointing the scanner *at* one of these directories is refused outright with a
  message and exit code `2`, rather than quietly auditing somebody else's code.
- Generated output and tool metadata are pruned too (`dist`, `build`, `target`,
  `.next`, `.nuxt`, `coverage`, `__pycache__`, caches, `.git`, IDE folders), and
  machine-generated files are skipped by name (`*.min.js`, `*.bundle.js`,
  `*_pb2.py`, `*.pb.go`, …). Unlike the vendor list, these names are only pruned
  when nested: a project directory that happens to be called `build` is still
  your code and stays scannable as an explicit root.
- Files over **5 MB** are skipped: at that size it is a bundle or a data blob,
  and reading it costs more than it can yield.

### Known limits

JS/TS regex literals are detected with the standard previous-token heuristic, so
a pattern like `/https:\/\//` no longer reads as a line comment. Template-literal
interpolations are still treated as opaque string content.

## 📦 Installation

### Via a Node package manager

| Manager | Command |
| ------- | ------- |
| npm     | `npm install -g todo-audit-skill` |
| pnpm    | `pnpm add -g todo-audit-skill` |
| yarn    | `yarn global add todo-audit-skill` |
| bun     | `bun add -g todo-audit-skill` |

A `postinstall` hook installs two things, because Claude Code reads them from
different places:

| Asset | Destination |
| ----- | ----------- |
| `SKILL.md` + the Python engine | `~/.claude/skills/todo-audit-skill/` |
| the three slash commands | `~/.claude/commands/todo/` → `/todo:audit`, `/todo:fix`, `/todo:analyze` |

Command files nested *inside* a skill directory are not discovered, so they are
installed alongside it rather than within it. Reinstalling replaces both
directories rather than merging, so a file dropped in a later release cannot
linger.

If install scripts are disabled (`--ignore-scripts`), run the installer manually:

```bash
npx todo-audit-skill-install    # or: node ./bin/installer.js
```

The engine runs on whatever `python3` is on your `PATH` (3.9+), with no runtime
dependencies. To have `.gitignore` honored as well, give that interpreter the one
optional package:

```bash
python3 -m pip install pathspec
```

Without it the scan still works — it falls back to the built-in denylist and
prints a one-line note on stderr, so ignored directories showing up is never
silent.

### 🔌 As a native Claude Code plugin

```bash
/plugin marketplace add arathus/todo
/plugin install todo@todo-audit-skill
```

The repo doubles as its own marketplace: `.claude-plugin/marketplace.json` is the
catalog and `.claude-plugin/plugin.json` is the plugin. The plugin is named
`todo` because plugin commands are namespaced by plugin name — that is what makes
them `/todo:audit` rather than `/todo-audit-skill:audit`.

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
uv run poe sync-version  # propagate the version to the JSON manifests
```

Quality bar: **ruff** (lint + format), **mypy `--strict`**, and **pytest** with
branch coverage gated at 85%. The scanner itself carries **zero runtime
dependencies** (`pathspec` is an optional extra for richer `.gitignore` support).

### Releasing

`src/todo_audit/__init__.py::__version__` is the single source of truth:
`pyproject.toml` reads it dynamically, and `poe sync-version` writes it into
`package.json` and `.claude-plugin/plugin.json`. A test fails if the three ever
disagree, so bumping one place and forgetting the others cannot ship.

## 📄 License & author

Licensed under [MIT](./LICENSE) · created by
[Ákos Jakub (arathus)](https://www.linkedin.com/in/akosjakub-710583112/)
