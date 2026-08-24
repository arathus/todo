---
description: Scan the codebase for TODOs and produce a triaged audit with suggested fixes.
allowed-tools: Bash, Read, Grep, Glob
---

# /todo:audit

Produce a severity-grouped audit of every TODO in the codebase, then a
suggested-fix table. **Read-only: never edit a file in this command.**

## Steps

1. **Scan.** Run the engine from the project root and parse its JSON:
   ```bash
   todo-audit scan . || {
     [ $? -eq 127 ] && PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/todo-audit-skill}/src" \
       python3 -m todo_audit.cli scan .
   }
   ```
   The engine audits only code the user wrote: dependency trees, virtual
   environments, build output, and generated files are excluded.

   Interpret the exit code rather than blindly falling through:
   - `0` — success, JSON is on stdout.
   - `2` — refused. Either the path does not exist, or it is third-party code.
     Read the stderr message and repoint; do **not** retry the other branch.
   - `127` — the console script is not installed; use the `PYTHONPATH` branch.

   Never discard stderr. A `note:` line there reports that `.gitignore` could
   not be applied, which means ignored files may appear in the results — relay
   it to the user instead of treating those extra hits as real.

2. **Read the summary first.** The payload carries `summary` (`by_type`,
   `by_scope`, `by_marker`, `files`) and `vocabulary` (the authoritative
   difficulty labels, fix kinds, and severity order). Use `vocabulary` verbatim
   rather than restating the scale from memory.

   Report the totals to the user before any detail.

3. **Scale the response to the count.** Report the full inventory, but only
   deep-dive as far as is useful:
   - **≤ 25 TODOs** — table every consolidated task.
   - **26–100** — table all urgent and question items; summarize plain ones by
     file with counts.
   - **> 100** — state the totals per file, then table the urgent items only,
     and tell the user the exact command to narrow the scan (for example
     `todo-audit scan src/payments`). Never silently truncate: if you table a
     subset, say how many were left out and why.

4. **List by severity.** Render a markdown list grouped and ordered
   `!TODO` (red) → `?TODO` (blue) → `TODO` (orange). One line per TODO:
   `` `file:line` [scope] in `symbol` — description``. Name the `marker`
   keyword when it is not plain `TODO`, and the `assignee` when present.

   `marker` is the keyword that produced the record: `TODO`, `FIXME`, `HACK`, or
   `XXX`. `FIXME` and `XXX` default to urgent and `HACK` to plain, and an
   explicit `!`/`?` sigil overrides that default. `assignee` holds the owner from
   the `TODO(alice):` form when one was given.

   Each record carries `symbol` (the enclosing function or class) — use it
   instead of opening the file when it already answers the question.

5. **Consolidate.** Group TODOs that describe parts of the same underlying fix
   into a single task. Note which raw TODOs each consolidated task covers, by
   `id` (a stable content hash) as well as by location.

6. **Rank & suggest.** For each task, read the surrounding code and produce a
   table row: TODO(s), scope/symbol, **difficulty (1–5)**, **suggested fix**,
   and **fix kind** (`system` or `temporary`), using the labels from
   `vocabulary`.

   Bound the reading: at most ~40 lines around each TODO, and read a whole file
   only when the snippet is genuinely insufficient. Say so when you do.

7. **Ask clarifying questions.** When code context is insufficient to propose a
   confident fix, ask the user targeted questions for those TODOs BEFORE
   finalizing their table rows. Do not guess.

## Output

- The totals from `summary`.
- A severity-grouped markdown list.
- A suggested-fix table (one row per consolidated task), each row marked as
  proposed — nothing is applied here.
- Any clarifying questions, clearly separated, for the user to answer.
- A closing line telling the user that `/todo:fix` applies these, and that it
  will ask for explicit approval first.

If `count` is `0`, say so plainly, state what was scanned, and stop. Do not
invent work, and do not run `/todo:analyze` unless asked.

Do not edit any files. Fixes are applied only by `/todo:fix`.
