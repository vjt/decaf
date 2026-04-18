---
name: start
description: Session start protocol — workflow gates, pending work, status report
---

Session start skill. Run the full workflow checklist and produce a
status report. This is the "what's pending" dashboard.

**Open with a freshly generated 4-word Italian profanity/blasphemy.**
Different every time. Creative. Vulgar. Sets the tone.

## Steps

### 1. Codebase review gate (the ONLY gate)

Count session headers (`## S`) in the active checkpoint. Check date
of last codebase review in `docs/reviews/codebase/`.

A review is **DUE** if:
- >= 12 sessions since last codebase review, OR
- > 2 weeks since last codebase review

**When due: must run before new feature work.** Bug fixes and deploy
fixes are exempt. This is enforced, not advisory.

### 2. Find active checkpoint

Find the checkpoint with `status: active` in `docs/checkpoints/`.
Report:
- CP number and how many sessions it has (count `## S` headers)
- Line count — warn if approaching 200 (time to rotate)
- Pending items listed at bottom of checkpoint

### 3. Read todo.md

Read `docs/todo.md` for the full backlog. Categorize by priority tier.

### 4. Check git status

```bash
git status
git log --oneline -5
```

Note any uncommitted changes, unpushed commits, or active worktrees.

### 5. Produce the report

Format the report as follows:

```
🔬 **Codebase Review**: not due (n sessions, last YYYY-MM-DD) / DUE — must run before features
📍 **Active Checkpoint**: CPnn (n sessions, ~nnn lines)
🌿 **Git State**: clean / uncommitted changes / unpushed commits

## Pending (from checkpoint)
- item 1
- item 2

## Todo Highlights
**Immediate**: ...
**High**: ...
**Medium**: ...
**Observation**: ...

## What's Available
Given the gate status, here's what we can work on: ...
```

The "What's Available" section is the key output — if a codebase
review is due, say so and offer to run it. Otherwise, list the
priority work from todo + checkpoint pending.
