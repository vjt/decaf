---
name: close
description: End-of-session protocol — push, checkpoint, docs, story episode
---

Session closing skill. Invoke with `/close` at end of session.

## Steps

### 1. Push unpushed commits

```bash
git log --oneline origin/master..HEAD
```

If commits exist, push to both remotes:
```bash
git push
```

### 2. Flush checkpoint

Find the active checkpoint (`status: active` in `docs/checkpoints/`).
Add a new session section (`## Sn:` with descriptive title and date).

Content for each session section:
- What was built/fixed (grouped by topic, not chronologically)
- Key technical decisions and why
- Bug fixes with root cause
- Stats line: test count, pyright errors, commit range

Use the existing checkpoint sections as format reference. Be concise
but complete — the checkpoint is the permanent record.

### 3. Update todo.md

- **DELETE completed items** — just the line, nothing else. No
  strikethroughs, no "RESOLVED" annotations. Completions go in
  checkpoint, not todo.
- **Keep all context on pending items** — design doc pointers, method
  names, extraction targets, scope details. These are actionable.
  Never strip context from pending work.
- **Fix stale references** — renamed tables, types, methods.
- Add new items discovered during work.
- Update wording of in-progress items if scope changed.

### 4. Check if checkpoint needs rotating

Count session headers (`## S`) and total lines in active checkpoint.

Rotate if ANY of:
- Active checkpoint has >= 8 sessions
- Active checkpoint exceeds ~200 lines
- The human asks to rotate

**Rotation procedure:**
1. Change `status: active` to `status: done` in frontmatter
2. Determine next CP number (increment from current)
3. Create new checkpoint file: `docs/checkpoints/YYYY-MM-DD-cpNN.md`
   with `status: active`, `# CPNN`, and `Previous:` line summarizing
   the closed checkpoint
4. Add `## State at checkpoint creation` with current stats
5. Commit: `docs: close CPxx, create CPyy`

### 5. Update living docs (if needed)

Check if this session's work affects any of these docs. Only update
if the content has actually changed:

- `docs/architecture.md` — new modules, tables, activities, endpoints
- `docs/strategy.md` — schedule changes, new cycle types
- `docs/patterns.md` — new patterns, changed infrastructure
- `docs/todo.md` — already handled in step 3

Skip docs that weren't affected. Don't touch docs for cosmetic reasons.

**Staleness check:** Grep active docs (architecture, strategy, patterns,
todo) for references to renamed/removed types, tables, methods, or
changed patterns from this session. Fix any stale references found.
Don't touch archive docs — they're historical records.

### 6. Project story episode (MANDATORY)

**Every session gets an episode.** There is always something to say —
a design decision, a debugging rabbit hole, a production surprise, a
moment where the plan met reality. Even "routine" sessions have a
story: why was this the priority, what was the tradeoff, what did we
learn. The project story is the narrative history of the codebase.
Gaps in the story are gaps in institutional memory.

Find the angle. Some sessions have obvious drama (production crashes,
reverts, architectural pivots). Others need you to look harder — the
small surprise that changed the approach, the assumption that turned
out wrong, the thing that was harder (or easier) than expected. If
nothing went wrong, write about what went *right* and why.

When writing:
- Read the last 2-3 episodes for voice and tone
- Update the header stats (commits, migrations)
- Extract any new laws for `docs/claude-lessons.md`
- **ALWAYS update `docs/project-evolution.md`** header stats (generated
  date, period, total commits, pace). This is mandatory every session,
  not "if significant."
- An episode without a law is fine. A law without an episode is not —
  laws need the narrative to give them weight.

### 7. Final commit and push

Commit all doc changes:
```
docs: close session — CP update + [whatever else changed]
```

Push to both remotes.

### 8. Report

Tell the human:
- Commits pushed (count + range)
- Checkpoint status (flushed / rotated + new created)
- Docs updated (list)
- Story episode (if written)
- Any pending work for next session
