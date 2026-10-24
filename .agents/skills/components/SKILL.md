---
name: components
description: Use when creating or changing React components or screens. Enforces splitting UI into small components, reusing existing ones, and never duplicating them or building big files.
---

# Components (Split, Reuse, Never Duplicate)

This rule is STRICT. It applies to every task that creates or changes UI.
Follow it before and during implementation. No exceptions.

## The 4 laws

1. **NEVER build one big file.** Every distinct piece of UI is its own component in its own file.
2. **NEVER write a new component's code inside another file.** A page or parent only imports and uses it.
3. **ALWAYS check if a component already exists. If it does, REUSE it.** Do not create a copy or a near-copy.
4. **Create a component ONLY when no existing one fits.**

## Mandatory pre-flight (do this BEFORE writing any code)

### Step 1: Break the request into pieces
List every UI piece the task needs (for example: page, table, row, form, form field, modal, badge, empty state). Each piece is a candidate component.

### Step 2: Search for what already exists
For EVERY piece in the list, actually search the project. Do not guess and do not rely on memory.
- List the component folders defined in `STRUCTURE.md` (generic UI, ERP feature components, AI components).
- Search by name AND by purpose (for example: a "status badge" may already exist as `Badge`, `StatusPill`, or `Tag`).
- Open the closest match and read its props before deciding.

### Step 3: Decide and report in a short table, BEFORE coding

| Piece | Decision | File |
| --- | --- | --- |
| Example: SaleRow | CREATE | `<path from STRUCTURE.md>/SaleRow.tsx` |
| Example: Button | REUSE | `<path from STRUCTURE.md>/Button.tsx` |
| Example: DataTable | EXTEND | `<path from STRUCTURE.md>/DataTable.tsx` (add optional `onRowClick`) |

Decisions allowed: **REUSE**, **EXTEND**, **CREATE**. Nothing else.

### Step 4: Build one component at a time
Create each component file completely, then move to the next. The page/parent file is written LAST and only composes the pieces.

## Decision rules

- **REUSE:** the existing component does the job as is, or with props it already has. Use it. Do not wrap it in a new component just to rename it.
- **EXTEND:** the existing component is almost right and needs one more option. Add a small OPTIONAL prop. The change must not break any current usage. Never rewrite or restyle it.
- **CREATE:** nothing existing fits. Create a new component in the correct folder (below). If the missing piece is a generic building block, it goes in `components/ui/` — read `DESIGN.md` and skill `design-system` first and follow them exactly.
- **NEVER** create a second component that does what an existing one already does, even with a different name or slightly different styling.
- If you are unsure whether an existing component fits, STOP and ask the developer. Do not duplicate to be safe.
- If the same JSX appears twice or more in your own code, extract it into a component immediately.

## File and size limits

- **One component per file.** The file name equals the component name (PascalCase).
- **Maximum 150 lines per component file.** If a file is going past 150 lines, STOP and split it into smaller components.
- A page or layout file (screens, layouts, or any route component registered in react-router, as defined in `STRUCTURE.md`) only composes components, wires data through hooks, and handles routing. It must not contain large JSX blocks or define components inline.
- Do NOT define a component inside another component's body.
- Do NOT put several unrelated components in one file, even if they are small.

## Keep concerns separate

- **Data fetching and API calls:** in the API layer (skill `api-server-state`) using the shared Axios instance, and consumed through TanStack Query hooks. Never call the API inline inside UI components.
- **Reusable logic:** in custom hooks, not mixed into JSX.
- **Types:** use the types generated from the repo-root `contracts/`. Never hand-write a shape that already exists there.
- **Design values:** follow `DESIGN.md` and skill `design-system`. No hardcoded colors or spacing when a token exists.
- Every component has explicit typed props. No `any`.

## Where a new component goes

The exact folder for each kind is defined in `STRUCTURE.md` (skill `project-structure`). Read it first. Never hardcode or invent a path.

| Kind | Rule |
| --- | --- |
| Generic building block (button, input, card, badge, modal shell) | Goes in the generic UI components folder (`components/ui/`) from `STRUCTURE.md`. This is the design system: reuse what exists first, and follow `DESIGN.md` + skill `design-system` when adding or changing anything there. |
| ERP feature piece (sales, purchasing, products, inventory, customers) | Goes in the ERP feature components folder from `STRUCTURE.md`, under its module |
| AI surfaces (`InsightCard`, `ForecastChart`, `AssistantChatPanel`, `ApprovalModal`) | The AI components folder (`components/ai/`) from `STRUCTURE.md`: import and use what exists; follow `DESIGN.md` + skill `design-system` before creating or changing anything here. |

If `STRUCTURE.md` does not say where a new component goes, STOP and ask. If the project already uses a convention for naming or exports, follow it.

## Forbidden (never do these)

- One large file that contains a whole screen's UI.
- Writing a new component's code inside the page or parent file.
- Creating a component without first searching for an existing one.
- Creating `NewButton`, `CustomTable`, `ButtonV2`, `MyCard`, or any copy of something that exists.
- Changing an existing shared component in a way that breaks its current usage.
- Skipping the decision table.

## Before you finish

End your reply with a short "Component check" section:
- **Reused:** existing components you used
- **Extended:** existing components you changed, and what you added
- **Created:** new components and their file paths
- Confirm that no file exceeds 150 lines and that no component is defined inside another file.
