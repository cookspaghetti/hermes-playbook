# Skill System Guide

Skills are the agent's **procedural memory** — reusable workflows written as markdown,
loaded on demand. Where memory stores *facts*, skills store *how to do things*.

## Anatomy of a Skill

```
~/.hermes/skills/
└── deploy-frontend/
    ├── SKILL.md          ← the skill itself
    ├── references/       ← optional deep-dive docs
    ├── templates/        ← optional fill-in-the-blank artifacts
    └── scripts/          ← optional executable helpers
```

`SKILL.md` is YAML frontmatter + markdown body. The system prompt sees each skill's
**name + description**; the body is loaded only when the skill is invoked. This matters:
your context budget is spent on the *index*, so the description must be a complete
trigger condition, not a teaser.

## What Belongs in a Skill

| Belongs | Doesn't belong |
|---|---|
| Multi-step procedures with exact commands | One-liner facts (that's memory) |
| Tool-specific gotchas you keep re-hitting | Session progress state |
| Verification steps ("how do I know it worked") | Anything stale in a week |
| Pitfalls ordered by how often they bite | Vague guidance without commands |

**The description discipline:** the first 57 characters are what shows in the system
prompt's skill index. The trigger must be *self-contained*: "Use when X. Then Y." —
not "About X."

## Maintenance Rules (learned by breaking them)

1. **Update on surprise.** Every time a skill's instructions turn out wrong or missing a
   step mid-use, patch it *immediately* — the next session won't remember what you learned.
2. **Skills rot silently.** A skill that encodes a command that stopped working is worse
   than no skill (confident wrongness). Periodically spot-execute one step per skill.
3. **Prefer patch over rewrite.** Skills accumulate hard-won pitfalls in odd corners;
   rewrites lose them.
4. **One skill = one workflow.** A skill that covers "deploy OR migrate OR debug" loads
   three workflows' worth of context for every use of any of them.

## Example Structure

```markdown
---
name: deploy-frontend
description: Use when deploying the web frontend to staging or prod. Handles build, upload, and health verification.
---

# Frontend Deployment

1. Build: `npm run build` (requires .env.production)
2. Upload: `./scripts/upload.sh staging`
3. **Verify**: GET /health returns 200 — if not, check [common failure table]
...
```

The verification step is what separates a skill from a note. "Deploy succeeded" is a
claim; "health endpoint returned 200" is evidence. Skills that end without evidence
produce confident, unverified work.