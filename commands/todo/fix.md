---
description: Apply the fixes established by a prior /todo:audit and route system-level items to CLAUDE.md.
---

# /todo:fix

Apply fixes decided in a `/todo:audit`.

## Steps

1. **Require an audit.** If no audit results are available in the conversation,
   STOP and tell the user to run `/todo:audit` first. Do not scan-and-fix blindly.

2. **Apply each fix.** For every task the audit approved:
   - Make the minimal code change implementing the suggested fix.
   - Remove the resolved TODO comment, or update it if only partially addressed.

3. **Route system-level fixes to CLAUDE.md.** For any fix classified `system`
   (typically difficulty 4–5, deferred to the future), append it to `CLAUDE.md`
   under a managed section, deduplicating against entries already present:

   ```markdown
   <!-- todo-audit:system-fixes:start -->
   ## System-level TODOs (managed by todo-audit-skill)
   - [ ] <source file:line> — <description of the system-level fix>
   <!-- todo-audit:system-fixes:end -->
   ```
   - Create the managed section if absent; otherwise insert new bullets into it.
   - Skip a bullet if an equivalent entry already exists (idempotent across runs).

4. **Do not persist temporary fixes.** Fixes classified `temporary` are applied
   in code only and never written to `CLAUDE.md`.

## Output

Summarize: which TODOs were fixed in code, which were appended to `CLAUDE.md`,
and which were skipped and why.
