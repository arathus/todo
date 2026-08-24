---
description: Apply the fixes established by a prior /todo:audit and route system-level items to CLAUDE.md.
---

# /todo:fix

Apply fixes decided in a `/todo:audit`. This command edits source files, so it
asks before it writes.

## Steps

1. **Require an audit.** If no audit results are available in the conversation,
   STOP and tell the user to run `/todo:audit` first. Do not scan-and-fix
   blindly.

2. **Get explicit approval — this is a hard gate.** An audit only *proposes*
   fixes; it never approves them. Before editing anything, present a numbered
   list of the fixes you intend to apply, each with its target
   `file:line`, its fix kind, and a one-line description of the edit. Then ask
   the user which to apply, and wait for an answer.

   Apply only what the user names. "Looks good" or "all of them" is approval for
   the whole list; silence, a question, or an unrelated reply is not. If the
   user approved a subset, do not touch the rest.

3. **Apply each approved fix.**
   - Make the minimal code change implementing the suggested fix.
   - Remove the resolved TODO comment, or update it if only partially addressed.

4. **Route system-level fixes to CLAUDE.md.** For any fix classified `system`
   (typically difficulty 4–5, deferred to the future), append it to `CLAUDE.md`
   under a managed section:

   ```markdown
   <!-- todo-audit:system-fixes:start -->
   ## System-level TODOs (managed by todo-audit-skill)
   - [ ] `<id>` <source file:line> — <description of the system-level fix>
   <!-- todo-audit:system-fixes:end -->
   ```
   - Create the managed section if absent; otherwise insert new bullets into it.
   - Deduplicate on the `id` from the scan payload, not on the text or the line
     number. `id` is a content hash that survives edits above the TODO, so
     matching on it is what makes repeated runs idempotent.
   - A deferred `system` fix is **not** resolved: leave its TODO comment in the
     code so the location is not lost, and rewrite it to reference the
     `CLAUDE.md` entry (for example `TODO: partial refunds — tracked in
     CLAUDE.md`). Only delete a comment whose work is actually done.

5. **Do not persist temporary fixes.** Fixes classified `temporary` are applied
   in code only and never written to `CLAUDE.md`.

6. **Verify before reporting success.** After editing, run the project's checks
   and report the real result:
   - Use the commands documented in `CLAUDE.md` or the project's config
     (for example `uv run poe test`, `npm test`, `make check`). If you cannot
     determine them, say so rather than claiming the change is verified.
   - If a check fails, show the failing output and either fix it or revert that
     edit. Never report a fix as complete on the strength of the edit alone.

7. **Re-scan.** Run the scanner again and confirm the resolved TODOs are gone
   and no new ones appeared.

## Output

Summarize: which TODOs were fixed in code, which were appended to `CLAUDE.md`,
which were skipped and why, and the verbatim result of the verification step.
