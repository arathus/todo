---
description: Check code against CLAUDE.md requirements and propose new TODOs where it diverges.
---

# /todo:analyze

Compare the codebase against the requirements the project has declared for
itself, and mark work that is needed to comply.

## Steps

1. **Load requirements from every place they live.** Claude Code itself reads
   more than one file, so checking only the root `CLAUDE.md` will miss projects
   that keep their conventions elsewhere. Read whichever of these exist:
   - `./CLAUDE.md` and `./.claude/CLAUDE.md`
   - `./CLAUDE.local.md`
   - `.claude/rules/*.md`
   - nested `<subdir>/CLAUDE.md` for the subtrees you are analyzing
   - `~/.claude/CLAUDE.md` — treat these as the user's personal preferences,
     lower priority than the project's own files, and never propose TODOs that
     exist only to satisfy them

   State which files you found. If none declare actionable requirements, report
   that and stop.

2. **Evaluate the code** against each requirement. Identify concrete locations
   where the code diverges from a stated requirement. Ignore the managed
   `todo-audit:system-fixes` section — those are already-tracked items, not
   fresh divergences.

3. **Propose TODOs as a diff.** For each divergence, prepare a TODO comment to
   insert at the relevant location:
   - Use the correct type marker: `!TODO:` for a required/urgent gap, `?TODO:`
     where investigation is needed, `TODO:` otherwise.
   - Use the target file's comment syntax.
   - Cite the requirement the TODO comes from, so a later reader knows why it
     exists.
   - Present ALL proposed insertions as a unified diff and ask the user to
     approve before writing. Do not edit files until approved. A subset approval
     means only that subset is written.

4. **Apply on approval.** After the user approves, insert the TODO comments.
   If the code already satisfies all requirements, insert nothing and say so.

5. **Confirm.** Re-run `todo-audit scan .` and show that the new markers are
   picked up at the locations you expect.

## Output

- The list of requirement files that were read.
- A unified diff of proposed TODO insertions (or "no changes needed").
- After approval: confirmation of inserted TODOs with their file:line.
