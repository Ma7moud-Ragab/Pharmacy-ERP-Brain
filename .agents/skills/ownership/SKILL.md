---
name: ownership
description: Use before editing any file, or when a task may touch something owned by another team: backend, Brain, infrastructure, documentation, or other teams' test suites.
---

# Ownership Boundaries

This rule is STRICT. It applies before you edit, create, move, or delete ANY file.

## The model

- **The frontend is ONE unit.** Everything inside `apps/erp-frontend/` belongs to the frontend team as a whole (Omar Mashhour and his teammates). There are **no per-person areas** inside it: any frontend team member — and the assistant working with one — may edit any file there, as long as the other skills are followed (`STRUCTURE.md`, `DESIGN.md`, `contracts-types`, `tech-stack`, ...).
- **Everything outside `apps/erp-frontend/` belongs to other teams.** It is READ-ONLY for the frontend. This is the router's "Strict Scope & Isolation" hard limit.

## Laws

1. **Edit freely inside `apps/erp-frontend/`** — the frontend team owns all of it. No folder inside it is reserved for a specific person.
2. **Everything outside it is read-only.** You may read it and use what it exports; you never edit, create in, move, or delete from it without first asking the developer ONE direct question about that exact file or area and getting a clear "yes" (router Scope rule).
3. **No approval path inside another team's area.** Even if the developer asks, do not edit it. Explain, and give him a message for the owner.
4. **Before editing an existing file, identify which area it belongs to.** If you are not sure, treat it as read-only and ask.
5. **If a task needs a change in another team's area, STOP** and report it (section "When a task crosses a boundary").
6. **NEVER copy another team's code into the frontend** to work around a boundary. That creates a duplicate (skill `components`).

## Read-only for the frontend (never edit)

| Area | Owner |
| --- | --- |
| **ERP backend (.NET)**: every module | Backend team |
| **Brain / AI service (Python)** | Brain team |
| **Infrastructure**: Docker, Compose, Nginx, CI/CD workflows, `.env.example` | Ali |
| **`CODEOWNERS`, `/docs`, and ADRs** | Team documents |
| **Other teams' test suites** (backend, contract tests, Brain tests) | Their owners |
| **Seed data scripts** | Not the frontend |
| **Repo-root `contracts/`** outside the frontend-owned slice | Backend / Brain teams |

Two frontend exceptions that are **not** free to edit, even though they sit inside or next to the frontend:
- `apps/erp-frontend/src/types/generated/` — generated, never edited by hand (skill `contracts-types`).
- The repo-root `contracts/` frontend slice — outside the app; edit only through one direct question and a clear "yes" (router Scope rule), following the contract-change protocol (skill `contracts-types`).

Using read-only code is allowed and expected: import it, render it, call it.

## How to know the area

1. Read `STRUCTURE.md` (skill `project-structure`) to see the folder map.
2. If the repo has a `CODEOWNERS` file, check it. It is the source of truth if it disagrees with this rule.
3. If it is still unclear, ask the developer. Do not guess.

## When a task crosses a boundary

STOP before editing. Tell the developer in this format:

> **Blocked by ownership:** what the task needs
> **Area and owner:** which area, and who owns it
> **Why I cannot do it:** one line
> **Message to send the owner:** a short ready-to-send message with the exact change or the missing item
> **What I can do meanwhile:** the part of the task inside the frontend app

Then continue with the part that is inside the frontend, if there is one.

## Forbidden (never do these)

- Editing, creating, moving, renaming, or deleting files outside `apps/erp-frontend/` without one direct question about that exact file/area and a clear "yes".
- Editing backend code, the Brain, or infrastructure files.
- Adding or changing environment variables in `.env.example` (ask Ali; the frontend only reads `VITE_` values).
- Editing `CODEOWNERS` or documentation under `/docs`.
- Editing generated types by hand, or hand-writing an API type (skill `contracts-types`).
- Rewriting or deleting another team's tests.
- Copying another team's code into the frontend as a workaround.
- Treating a request from the developer as permission to cross a boundary.

## Before you finish

End your reply with a short "Ownership check" section:
- Confirm that every file you changed is inside `apps/erp-frontend/` (or an approved exception)
- Anything blocked by ownership, with the message for the owner
