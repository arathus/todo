---
description: Scan the codebase for TODOs and produce a triaged audit with suggested fixes.
---

# /todo:audit

Produce a severity-grouped audit of every TODO in the codebase, then a
suggested-fix table.

## Steps

1. **Scan.** Run the engine from the project root and parse its JSON:
   ```bash
   todo-audit scan . 2>/dev/null || PYTHONPATH=src python3 -m todo_audit.cli scan .
   ```
   Each record has `file`, `line`, `type`, `scope`, `description`, `color`.

2. **List by severity.** Render a markdown list grouped and ordered
   `!TODO` (red) → `?TODO` (blue) → `TODO` (orange). State, per file, which
   severity of TODOs it holds. One line per TODO: `` `file:line` [scope] — description``.

3. **Consolidate.** Group TODOs that describe parts of the same underlying fix
   into a single task. Note which raw TODOs each consolidated task covers.

4. **Rank & suggest.** For each task, read the surrounding code context and
   produce a table row: TODO(s), scope, **difficulty (1–5)**, **suggested fix**,
   and **fix kind** (`system` or `temporary`).
   - Difficulty: 1 immediate · 2 refactor · 3 minor rewrite · 4 module/system rewrite · 5 redesign.
   - `system` = a future, system-level concern (usually difficulty 4–5); `temporary` = a local throwaway fix.

5. **Ask clarifying questions.** When code context is insufficient to propose a
   confident fix, ask the user targeted questions for those TODOs BEFORE
   finalizing their table rows. Do not guess.

## Output

- A severity-grouped markdown list.
- A suggested-fix table (one row per consolidated task).
- Any clarifying questions, clearly separated, for the user to answer.

Do not edit any files. Fixes are applied only by `/todo:fix`.
