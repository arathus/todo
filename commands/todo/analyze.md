---
description: Check code against CLAUDE.md requirements and propose new TODOs where it diverges.
---

# /todo:analyze

Compare the codebase against the requirements declared in `CLAUDE.md` and mark
work that is needed to comply.

## Steps

1. **Load requirements.** Read `CLAUDE.md`. If it declares no actionable
   requirements, report that and stop.

2. **Evaluate the code** against each requirement. Identify concrete locations
   where the code diverges from a stated requirement.

3. **Propose TODOs as a diff.** For each divergence, prepare a TODO comment to
   insert at the relevant location:
   - Use the correct type marker: `!TODO:` for a required/urgent gap, `?TODO:`
     where investigation is needed, `TODO:` otherwise.
   - Use the target file's comment syntax.
   - Present ALL proposed insertions as a unified diff and ask the user to
     approve before writing. Do not edit files until approved.

4. **Apply on approval.** After the user approves, insert the TODO comments.
   If the code already satisfies all requirements, insert nothing and say so.

## Output

- A unified diff of proposed TODO insertions (or "no changes needed").
- After approval: confirmation of inserted TODOs with their file:line.
