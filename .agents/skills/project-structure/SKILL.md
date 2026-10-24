---
name: project-structure
description: Use whenever creating, moving, renaming, or importing files or folders. Requires reading STRUCTURE.md first.
---

# Project Structure

`STRUCTURE.md` is the single source of truth for the project's folder structure, file placement, naming, and import rules.
You must read it BEFORE you create, move, rename, or import any file. No exceptions.
This rule does NOT define the structure. It only tells you how to follow `STRUCTURE.md`.

## 1. What counts as a structure task

This rule applies whenever a task:
- Creates a new file or folder (component, page, hook, store, API file, type, test, asset, config)
- Moves or renames a file or folder
- Adds an import between files in different folders
- Decides where a piece of code should live

If you are unsure, treat it as a structure task.

## 2. Mandatory pre-flight (do this in order)

1. **Read `STRUCTURE.md` in full.** Use the file-reading tool on the actual file. Do not rely on memory, on earlier conversation turns, or on assumptions.
2. **Re-read it at the start of every new task**, even if you read it earlier in the same session. The file can change between tasks.
3. **State in one short line** where each new file will go and which part of `STRUCTURE.md` says so.
4. Only then create or change files.

## 3. While working

- Put every file exactly where `STRUCTURE.md` says. Use the naming rules and import rules in it, if it defines them.
- Look at the real folder tree before creating anything, so you do not create a duplicate file or folder.
- Any folder or file path written in the OTHER skills is only an example. `STRUCTURE.md` always wins when they differ.

## 4. When `STRUCTURE.md` is missing or does not cover the case

- If `STRUCTURE.md` is missing, empty, or unreadable: **stop and tell the developer.** Do not guess a structure.
- If it has no place for what you need to create: **stop and ask.** Suggest the place that fits best, and wait for the answer.
- If the real project tree differs from `STRUCTURE.md`: follow `STRUCTURE.md`, and tell the developer about the difference. Do not reorganize anything yourself.
- **Never edit `STRUCTURE.md`** unless the developer explicitly asks you to. If you think it needs a change, suggest it in your reply.
- If a request contradicts `STRUCTURE.md`, point out the conflict and ask which one wins before continuing.

## 5. Always forbidden

- Creating a file outside the places `STRUCTURE.md` allows.
- Creating a new top-level folder without the developer's approval.
- Creating dumping-ground folders such as `utils/`, `helpers/`, `common/`, `misc/`, `shared/`, `temp/`, unless `STRUCTURE.md` explicitly defines them.
- Moving, renaming, or deleting existing files on your own.
- Circular imports, or any import that `STRUCTURE.md` does not allow.
- Vague or throwaway names such as `temp.tsx`, `test.tsx`, `new-*.tsx`, `*-copy.tsx`, `index2.tsx`.
- Creating a duplicate of a file that already exists elsewhere.

## 6. Environment and secrets

- Environment values are read only through `import.meta.env.VITE_*`.
- Only `.env.example` is committed. Never create, edit, or print real `.env` values.
- Never put secrets in frontend code. Anything with the `VITE_` prefix is public in the browser bundle.

## 7. What `STRUCTURE.md` should contain

This list is for the team, so the file gives you everything you need. If a part is missing, ask the developer instead of guessing:
- The folder tree
- Where each kind of file goes (screen, component, hook, API file, store, type, test)
- Naming rules for files, folders, and exports
- Which folders may import from which
- Where tests live

## 8. Before you finish

End your reply with a short "Structure check" section:
- Every file you created, with its path
- Which part of `STRUCTURE.md` placed each one
- Any difference you noticed between `STRUCTURE.md` and the real project
- Any case `STRUCTURE.md` does not cover that needs a decision
