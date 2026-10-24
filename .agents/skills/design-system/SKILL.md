---
name: design-system
description: Use before creating or modifying any UI: pages, components, styles, colors, typography, spacing, icons, states, or visible text. Requires reading DESIGN.md first.
---

# Design System Gate

`DESIGN.md` is the single source of truth for how this product looks and feels.
You must read it BEFORE you create or modify anything visual. No exceptions.

## 1. What counts as UI work

This rule applies whenever a task touches any of the following:

- Pages, layouts, routes (`features/*/pages`, `layouts/`, `routes/`)
- React components, including `features/*/components/*`, `components/ui/*`, and `components/ai/*`
- Styles: CSS, Tailwind classes, theme files, design tokens
- Colors, typography, spacing, radius, shadows, icons, images, animations
- Forms, tables, modals, empty states, loading states, error states
- User-facing text inside the UI (labels, buttons, messages)

If the task is pure logic with zero visual impact (types, API clients, hooks without markup), this rule does not apply.
If you are unsure, treat it as UI work.

## 2. Mandatory pre-flight (do this in order)

1. **Read `DESIGN.md` in full.** Use the file-reading tool on the actual file. Do not rely on memory, on earlier conversation turns, or on assumptions about what it contains.
   - `DESIGN.md` is a handoff written against the design prototype: the file references inside it (for example `src/design-system.tsx`, `src/index.css`) belong to the prototype, not to this app. Always map what you build to `STRUCTURE.md`.
   - Respect its "Verification key": values marked "Needs verification in Figma" are not settled. Ask; never invent them.
   - The "logged-in user is Mahmoud Ragab" line (and its checklist item) is prototype sample data. In this app the logged-in user is whoever authenticates (skill `routing-auth`); never hardcode a user identity in the UI.
2. **Re-read it at the start of every new task**, even if you read it earlier in the same session. The file can change between tasks.
3. **State your plan in one short line before writing code**, naming which parts of `DESIGN.md` you will apply (for example: tokens, a specific component pattern, typography scale, spacing rules).
4. Only then create or modify the UI.

## 3. While implementing

- Use the tokens, components, and patterns defined in `DESIGN.md`. Do not hardcode colors, font sizes, spacing, radius, or shadows when a token exists.
- Tokens are defined ONCE as CSS variables in the Tailwind entry — the file that imports `tailwindcss` (its path is in `STRUCTURE.md`). Reference the variables; never re-declare a token inside a component.
- Reuse existing primitives from `components/ui/*` before creating a new one.
- Do not invent a new visual pattern when `DESIGN.md` already defines one for that case.
- Keep the same look and behavior across ERP screens. A new screen must feel like part of the same product.
- Cover all states the design defines: default, hover, focus, disabled, loading, empty, and error.

## 4. Accessibility and POS/ERP Keyboard Workflows

High-throughput ERP screens (cashier POS, inventory scanning, order desks) require rapid keyboard navigation and hardware scanner support:

### A. Focus Traps and Modal Dialogs
- All modal dialogs, drawers, and overlay menus (e.g., Radix UI primitives) must trap focus within the modal while open.
- When closed, focus must automatically return to the trigger element that opened the dialog.
- The `Escape` key must dismiss any open modal, dropdown, or popover without submitting data.

### B. Global Key Bindings & POS Shortcuts
- Support standard ERP hotkeys:
  - `Enter`: Submit focused form, complete quick action, or trigger barcode lookup.
  - `Escape`: Cancel operation, dismiss modal, or clear search/cart focus.
  - Function keys (`F1`–`F12`): Cashier action triggers (e.g., `F2` Checkout/Pay, `F4` Discount, `F8` Hold/Park).
- Global key listeners must call `e.preventDefault()` when handling function keys or custom shortcuts to prevent default browser behavior.
- Scoping rule: Global hotkeys must be ignored when the user is typing inside an active `<input>`, `<textarea>`, or content-editable field, unless the shortcut is specifically intended for that field.

### C. Barcode Scanner Input Buffers
- Physical USB/Bluetooth barcode scanners emulate keyboard input, sending rapid alphanumeric keystrokes followed immediately by an `Enter` key (keystroke interval typically < 50ms).
- Do NOT require cashiers to manually click into a specific barcode input field.
- Implement a global buffer listener that detects rapid sequential keystrokes (< 50ms interval):
  - If characters accumulate rapidly and terminate with `Enter`, treat the sequence as a hardware scan.
  - Route the scanned barcode directly to the POS cart/search action and reset the buffer.
  - Normal human typing (keystroke interval > 80ms) must not trigger scanner logic.

## 5. When `DESIGN.md` does not cover the case

- If `DESIGN.md` is missing, empty, or unreadable: **stop and tell the user.** Do not proceed with your own style.
- If `DESIGN.md` has no guidance for what you need: **stop and ask**, or propose the smallest option consistent with the existing rules and clearly mark it as a proposal.
- **Never edit `DESIGN.md` yourself** unless the user explicitly asks you to. If you think it needs a change, suggest the change in your reply instead.
- If a user request contradicts `DESIGN.md`, point out the conflict and ask which one wins before continuing.

## 6. Before you finish

Re-check your work against `DESIGN.md`, then end your reply with a short "Design check" section:

- Which parts of `DESIGN.md` you applied
- Any deviation, with the reason
- Any gap you found in `DESIGN.md` that needs a decision from the team
- Confirm that accessibility, focus traps, and keyboard shortcuts follow Section 4

