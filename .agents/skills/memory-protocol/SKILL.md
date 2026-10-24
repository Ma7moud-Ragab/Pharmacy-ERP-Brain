---
name: memory-protocol
description: Use at the start of every new task and after finishing a task that changed something. Covers asking about reading MEMORY.md, logging entries with exact time and developer name, and reporting frontend changes that arrived through git pull.
---

# Memory Protocol

`MEMORY.md` is the developer's PERSONAL, local-only log (it is in `.gitignore`).
You never read its `## Log` section or write to it on your own. The developer decides every time.

## 0. After a pull: check what the team changed

Goal: if teammates added or changed something in the watched paths (for example a new component), offer to record it in memory.

### When to check
- At the start of every new task, before section 1.
- Immediately, if the developer says they pulled or updated the project.

### How to check (read-only git commands only)
1. Read `Last synced commit` and `Watched paths` from the `## Sync` section of `MEMORY.md`. Reading these two lines is always allowed.
   - If `Watched paths` is empty, ask the developer which folders to watch (use `STRUCTURE.md` as a guide), write the answer on that line, and continue. Never assume a folder.
2. Run `git rev-parse HEAD`.
   - Same as `Last synced commit`: nothing new. Skip to section 1 without mentioning it.
   - `Last synced commit` is empty: ask "Do you want me to set the current commit as your starting point? (yes / no)". If yes, write the current HEAD there. Do not log any history.
   - Different: continue below.
3. Run, limited to the watched paths:
   - `git log --format="%h | %an | %ad | %s" --date=iso <synced>..HEAD -- <watched paths>`
   - `git diff --name-status <synced> HEAD -- <watched paths>`
4. If the synced commit cannot be found (history was rewritten), tell the developer and offer to reset the starting point to the current HEAD.

### Ignore the noise
Skip lock files (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`), build output (`.next/`, `dist/`, `node_modules/`), source maps, and `MEMORY.md` itself.

### What to do with the result
- **No relevant changes in the watched paths:** say in one line "New commits arrived, but nothing changed in the watched paths", update `Last synced commit` to the current HEAD, and continue.
- **Relevant changes:** summarize them by author in a few lines. Focus on what matters: new or removed components, pages and routes, hooks, API client or generated types, shared UI primitives, config. For a new component, open the file briefly to describe what it does in one line. Then ask:

> Do you want me to record these changes in MEMORY.md? (yes / no / only some)

  - **Yes or only some:** write one entry per change group using the "Team change" template in section 3.
  - **No:** do not log them.
  - In every case, after the developer answers, update `Last synced commit` to the current HEAD so you do not ask about the same changes again.

### Git safety
Only read-only commands are allowed here: `git rev-parse`, `git log`, `git diff`, `git show`, `git status`.
Never run `git pull`, `fetch`, `merge`, `rebase`, `checkout`, `reset`, `stash`, `commit`, or `push`.

## 1. Before executing any request: ask about reading

At the start of every new task, BEFORE doing any work (after section 0), ask the developer exactly this:

> Do you want me to read MEMORY.md before I start? (yes / no)

- **Yes:** read `MEMORY.md` fully. Summarize in 2-3 lines what is relevant to the current task. Then continue.
- **No:** do NOT open the `## Log` section. Continue without it.
- **No answer yet:** wait. Do not start the task until the developer answers.
- **Purely read-only, informational, or strategic-analysis prompts:** bypass sections 0 and 1 and answer directly (router §1, Memory hard limit). Planning, reviews, and questions that change no files are included.
- Ask once per task, not once per step. Do not ask again until the developer gives a new task.

If a task also involves UI work, ask this question first, then follow skill `design-system` (read `DESIGN.md`).

## 2. After finishing: ask about logging

When the task is done, BEFORE writing anything to the log, ask:

> Do you want me to log this update in MEMORY.md? (yes / no)

- **Yes:** write the entry as described in section 3.
- **No:** do NOT touch the `## Log` section.
- Only ask for tasks that changed something (code, files, config, decisions). Do not ask for pure questions or explanations.

## 3. How to write an entry

When the developer says yes:

1. **Developer name:** read the `Developer name:` field in `MEMORY.md` and use it exactly as written. Do not shorten, translate, or guess it. If the field is empty, ask the developer for their name and write it there first. Reading this field is allowed even if the developer said "no" to reading the memory.
2. **Exact time:** get the real time from the terminal — on Windows (PowerShell): `Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"`; on Unix: `date +"%Y-%m-%d %H:%M:%S %z"`. Never guess, estimate, or reuse an earlier timestamp. The time is the moment the task was executed.
3. **Append at the end** of the `## Log` section. Never insert in the middle, and never edit, reorder, or delete existing entries.

### Entry template (work done in this session)

```
### <Developer name> - [YYYY-MM-DD HH:MM:SS +ZZZZ]
- **Task:** what was requested, in one line
- **Done:** what was actually changed, in 1-3 lines
- **Files:** list of files created / modified / deleted
- **Notes:** decisions, gotchas, or follow-ups (write "none" if empty)
```

### Entry template (team change found after a pull)

```
### Team change (pulled) - [YYYY-MM-DD HH:MM:SS +ZZZZ]
- **Recorded by:** <Developer name>
- **From:** <git author name> (commit <short hash>, committed <commit date>)
- **Added / Modified / Removed:** file paths
- **What it is:** one line, for example "ApprovalModal component, shows an ActionProposal and posts the approval"
- **Notes:** anything I need to know before using it (write "none" if empty)
```

## 4. Hard rules

- Never read the `## Log` section without a "yes" from the developer.
- Never write log entries without a "yes" from the developer.
- The only write allowed without asking is updating the `Last synced commit` line, as described in section 0.
- Never invent entries for work you did not do or changes you did not see in git.
- Never log secrets, tokens, passwords, or `.env` values.
- Keep entries short. The log is a summary, not a copy of the code.
