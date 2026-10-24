---
name: contracts-types
description: Use when using or needing types for API data, entities, endpoints, or anything from the repo-root contracts/ folder, including generated types and fields missing from a contract.
---

# Contracts and Types

This rule is STRICT. It applies to every task that touches data from the backend.
The shared contracts in the repo-root `contracts/` folder are the single source of truth for API shapes.
The frontend gets its types ONLY from the files generated from them (skill `tech-stack`: `json-schema-to-typescript` and `openapi-typescript`).

## The 5 laws

1. **NEVER hand-write a type for an API shape.** If it exists in the repo-root `contracts/`, you use the generated type.
2. **NEVER edit a generated file.** Not even a small fix.
3. **NEVER modify the repo-root `contracts/` on your own.** You can read it. Changes happen ONLY through the router's Scope rule (one direct question about that exact file + a clear "yes") and deal ONLY with the frontend-owned slice: `openapi.erp.yaml`, `FRONTEND.md`, `schemas/`, `fixtures/`. Everything else in `contracts/` stays read-only, full stop.
4. **NEVER work around a missing or wrong type** with `any`, `as` casts, `@ts-ignore`, or a made-up local type.
5. **If the contract is missing something, STOP and tell the developer.**

## Where things live

| What | Where |
| --- | --- |
| The contracts (read-only by default; frontend-owned slice = ask first) | repo-root `contracts/` (in the app via the `@contracts/*` alias) |
| Generated types (never edit) | The generated types location in `STRUCTURE.md` |
| Short alias exports of generated types | The aliases file in `STRUCTURE.md` |
| Frontend-only types (UI) | Next to the component, or where `STRUCTURE.md` says |

Where each file goes is defined in `STRUCTURE.md` (skill `project-structure`). Read it before creating a file. Never hardcode or invent a path.

## Before using any API data: find the type first

1. Search the generated files for the type you need (entity shape or endpoint request/response).
2. If it exists, import it with `import type` and use it. Do not copy its fields into a new type.
3. If you want a shorter name, add a re-export alias in the aliases file (see `STRUCTURE.md`) that points to the generated type. An alias is allowed. A copy is not.
4. Build variations from the generated type instead of re-typing fields: `Pick`, `Omit`, `Partial`, `Extract`, indexed access.

```ts
// Allowed: alias and derived types
import type { components } from './generated/erp'
export type Sale = components['schemas']['Sale']
export type SaleSummary = Pick<Sale, 'id' | 'total' | 'created_at'>

// Forbidden: re-typing a field list by hand
type Sale = { id: string; total: number; created_at: string }
```

## What you may write by hand

Only types that are NOT API shapes:
- Component props
- UI state and view models (for example a cart row with a local `isSelected` flag)
- Form values (derive them from the Zod schema with `z.infer`; the request payload sent to the API still uses the generated type)
- Utility and helper types

Even then, if a UI type contains fields that exist in a contract type, build it from the generated type.

## When the type is missing, wrong, or outdated

STOP. Do not guess and do not continue with a workaround. Tell the developer using this format:

> **Missing or wrong in the contract:** the entity or endpoint and the field
> **What I need:** the type, field, or value I expected
> **What I found:** what the generated type or contract currently says
> **Who should fix it:** in the repo-root `contracts/` — the backend owner of that module, or the developer directly if the change is in the frontend-owned slice (needs the Scope rule's direct question + clear "yes" first)

Then wait. The developer decides who fixes the contract, and the types get regenerated.

### Regenerating types
- Endpoint/path types: `npm run codegen:paths` (openapi-typescript, from the repo-root `openapi.erp.yaml` → `src/types/generated/api-paths.ts`).
- Entity types: generated from the repo-root `contracts/schemas/` with json-schema-to-typescript (installed). No npm script yet — treat it as a deliberate manual task.
- Ask the developer before regenerating, because it can rewrite many files. Never do it silently.
- If the contracts changed after the generated files were last created (for example after a pull), tell the developer that the types may need regeneration.
- If a regeneration causes TypeScript errors, fix YOUR usage in the code. Never edit the generated type to make the error disappear.

## Value formats

- Use the formats the contract defines for ids, dates, money, and quantities. Do not assume them.
- Convert for display only, at the UI edge (for example formatting a date string for the screen). Never change the shape of the data in the API layer.
- Use the contract's enums and string unions. Do not retype them as plain `string`.

## Forbidden (never do these)

- Hand-written `interface` or `type` for an entity or endpoint that exists in the repo-root `contracts/`.
- Editing, reformatting, or "cleaning up" a file in the generated types folder.
- Editing any file under the repo-root `contracts/` without the Scope rule's one direct question and a clear "yes".
- `any`, `unknown as X`, `as SomeType` casts, or `@ts-ignore` / `@ts-expect-error` to silence a contract mismatch.
- Adding an optional `?` to a field only because it is missing from the generated type.
- Duplicating the same API type in two places.
- Inventing a field that is not in the contract.

## Before you finish

End your reply with a short "Types check" section:
- Which generated types you used
- Any alias you added, and the file you added it to
- Any hand-written type you created, and why it is not an API shape
- Any gap you found in the contracts that needs the backend owner
