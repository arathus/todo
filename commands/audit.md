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
   explicit `!`/`?` sigil overrides that default — on either side of the keyword,
   so `TODO!:` and `!TODO:` are the same marker. `assignee` holds the owner from
   the `TODO(alice):` form when one was given.

   Each record carries `symbol` (the enclosing function or class) — use it
   instead of opening the file when it already answers the question.

5. **Consolidate.** Group TODOs that describe parts of the same underlying fix
   into a single task. Note which raw TODOs each consolidated task covers, by
   `id` (a stable content hash) as well as by location.

6. **Rank each task, and render a real markdown table.** One row per
   consolidated task, with exactly these columns:

   ```markdown
   | # | TODO(s) | Location | Symbol | Diff. | Kind | Summary |
   | - | ------- | -------- | ------ | ----- | ---- | ------- |
   | 1 | `5000f3fe` | `piccolo_app.py:9` | module | 2 | system | Keep the split; delete the stale TODO |
   | 2 | `5c869754` | `piccolo_conf.py:17` | `_engine_config_from_url` | 1 | temporary | Inline the URL-parse dict into the caller |
   | 3 | `ebe4ed6a` `08f0a135` | `evaluation.py:37-38` | module | 3 | system | Move scale semantics into `Field(description=…)` |
   ```

   Rules for the table, all mandatory:
   - It **must** be a pipe table with a header separator row. Never substitute a
     list, and never emit per-task `Field: value` blocks in its place. If you
     find yourself writing `Diff.: 2` on its own line, you have produced the
     wrong shape — go back and build the table.
   - Every cell is **short and single-line**: no newlines, no bullet lists, no
     paragraphs. `Summary` is one imperative clause, ≤ 60 characters. Truncate
     the first 8 characters of each `id`.
   - The prose belongs in step 7, not in a cell. Cells that grow into sentences
     are what destroys the alignment in a terminal.
   - `Diff.` is the difficulty digit alone; `Kind` is `system` or `temporary`.

7. **Then write a detail block per task — this is where you are talkative.**
   Below the table, one `#### N. <summary>` section per row, in table order.
   Each block covers all of the following, and names real identifiers from the
   code you read rather than describing them generically:

   - **Change:** the concrete edit. Which files, which symbols, what the code
     becomes. Enough that a reader could apply it without re-deriving it.
   - **Why:** the reasoning from the code you actually read — the convention it
     follows, the caller that constrains it, the invariant it protects. Not a
     restatement of the TODO text.
   - **Risk:** what could break, what you are unsure of, and any alternative you
     considered and rejected *with the reason*. Write "none identified" only when
     that is true.
   - **Verify:** how the user will know it worked — the test to run, the command,
     or the observable behavior.

   Length follows difficulty: roughly 2–4 sentences for difficulty 1–2, and a
   fuller treatment for 3–5, where the design tradeoff is the valuable part. Do
   not pad — if a fix is genuinely one line, say so in one line and move on. But
   a bare imperative with no reasoning behind it is not an acceptable fix
   proposal; if you cannot explain why, that is a clarifying question instead.

   Bound the reading: at most ~40 lines around each TODO, and read a whole file
   only when the snippet is genuinely insufficient. Say so when you do.

8. **Ask clarifying questions.** When code context is insufficient to propose a
   confident fix, ask the user targeted questions for those TODOs BEFORE
   finalizing their rows. Do not guess, and do not invent a confident-sounding
   fix to fill the row.

## Output

In this order:

1. The totals from `summary`.
2. A severity-grouped markdown list.
3. The suggested-fix **table** — one row per consolidated task, short cells.
4. The per-task **detail blocks**, covering Change / Why / Risk / Verify.
5. Any clarifying questions, clearly separated, for the user to answer.
6. A closing line: nothing has been applied, `/todo:fix` applies these, and it
   will ask for explicit approval first.

The table is for scanning; the detail blocks are for deciding. Emitting only one
of the two is a failed audit — the table without the blocks gives the user no
basis to approve, and the blocks without the table give them nothing to scan.

If `count` is `0`, say so plainly, state what was scanned, and stop. Do not
invent work, and do not run `/todo:analyze` unless asked.

Do not edit any files. Fixes are applied only by `/todo:fix`.

## Worked example of the expected shape

````markdown
**3 TODOs** across 2 files — 2 urgent, 1 question. Markers: 2 TODO, 1 FIXME.

### !TODO (urgent)
- `piccolo_conf.py:17` [function] in `_engine_config_from_url` — collapse this helper
- `evaluation.py:37` [module] `FIXME` — scale semantics live only in comments

### ?TODO (question)
- `vcc_metadata.py:85` [function] in `_to_float` — should pydantic coerce this?

| # | TODO(s) | Location | Symbol | Diff. | Kind | Summary |
| - | ------- | -------- | ------ | ----- | ---- | ------- |
| 1 | `5c869754` | `piccolo_conf.py:17` | `_engine_config_from_url` | 1 | temporary | Inline the URL-parse dict into the caller |
| 2 | `ebe4ed6a` | `evaluation.py:37` | module | 3 | system | Move scale semantics into `Field(description=…)` |
| 3 | `83da9737` | `vcc_metadata.py:85` | `_to_float` | 2 | temporary | Replace the helper with a `BeforeValidator` |

#### 1. Inline the URL-parse dict into the caller

- **Change:** delete `_engine_config_from_url` and pass its dict literal directly
  to the single `PostgresEngine(config={...})` call in `piccolo_conf.py:31`.
- **Why:** the helper has exactly one caller and no branching, so the indirection
  buys nothing; the surrounding module keeps its other config inline already.
- **Risk:** none identified beyond an import — confirm no test imports the helper
  by name before deleting it.
- **Verify:** `uv run poe test`, plus a startup check that the engine still
  connects.

#### 2. Move scale semantics into `Field(description=…)`

- **Change:** in `evaluation.py`, hoist the scoring-scale comments above each of
  the ~89 fields into `Field(..., description="…")`, reusing the existing
  Hungarian scale text verbatim. Give the same treatment to the handful of fields
  in the sibling models.
- **Why:** the comments are the only record of what each score means, so they are
  invisible to anything that reads the schema — API docs, editor hovers, and the
  JSON Schema export all lose them today. `Field(description=…)` is the place
  pydantic already looks.
- **Risk:** 89 mechanical edits is a large diff and easy to get subtly wrong; the
  scale text is user-facing Hungarian, so it must be copied, not paraphrased. I
  considered a module-level docstring table instead, but that keeps the same
  invisibility problem the TODO is complaining about.
- **Verify:** the generated JSON Schema carries a description for every scored
  field, and a spot check of three fields against the removed comments.
````

Note what the example does: the table stays narrow enough to align in a terminal,
and every sentence of reasoning lives in the detail block underneath.
