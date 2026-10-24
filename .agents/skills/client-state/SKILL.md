---
name: client-state
description: Use when working with Zustand stores, the POS cart, or the logged-in user state.
---

# Client State (Zustand)

This rule is STRICT. It applies to every task that touches global client state.
Server data belongs to TanStack Query (skill `api-server-state`). Zustand is NOT a place for it.

## The 5 laws

1. **Zustand has exactly TWO stores:** the POS cart and the auth state. Creating any other store needs the developer's approval.
2. **NEVER put server data in a store.** Lists, details, and anything fetched from the API stay in TanStack Query.
3. **ALWAYS subscribe with a selector.** Never subscribe to the whole store.
4. **NEVER mutate state.** Updates are immutable and happen only inside store actions.
5. **NEVER call the API from inside a store** — the ONE exception is the auth store's session actions (`login`, `logout`, `initialize`), which call the auth service by design (skill `routing-auth`). Everything else lives in hooks (skill `api-server-state`).

## The two stores

| Store | Holds |
| --- | --- |
| **Cart** | POS cart items |
| **Auth** | The logged-in user (`currentUser`), roles, and session flags (`isAuthenticated`, `isInitializing`). The token itself lives in the token storage file, never in the store. |

- One store per file. The hook is named `use<Name>Store` (for example `useCartStore`).
- Where each file goes is defined in `STRUCTURE.md` (skill `project-structure`). Read it before creating a file. Never hardcode or invent a path.

## Store structure

- Use `create<State>()(...)` with an explicit `State` interface that contains both the data and the actions.
- Actions are named by intent: `addItem`, `removeItem`, `updateQuantity`, `clearCart`, `login`, `logout`, `initialize`. Do NOT expose a generic `setState` or a setter for every field.
- Use the types generated from the repo-root `contracts/` for any shape that comes from the API, such as the user, roles, and product ids (skill `contracts-types`). No `any`.

## Selectors (mandatory)

```ts
// Correct: subscribe only to what you need
const items = useCartStore((s) => s.items)
const addItem = useCartStore((s) => s.addItem)

// Correct: several values in one selector
const { items, clearCart } = useCartStore(useShallow((s) => ({ items: s.items, clearCart: s.clearCart })))

// Forbidden: whole-store subscription
const store = useCartStore()
```

- If a selector returns a new object or array, wrap it with `useShallow` (Zustand v5). Otherwise the component re-renders endlessly.
- Check the installed Zustand version before writing syntax (skill `tech-stack`).

## Derived values

- Do NOT store anything that can be computed: item count, subtotal, totals. Compute it in a selector or a small helper function.
- Cart totals are for display only. What is sent to the API follows the contract (skill `contracts-types`), not the UI numbers.
- Keep cart items minimal: the product id, the quantity, and only the fields needed to display the row.

## Cart rules

- After a successful sale, clear the cart from the mutation's `onSuccess` (skill `api-server-state`), not from the store itself.
- Quantity must stay a valid positive number. Adding an item that is already in the cart increases its quantity; it never creates a duplicate row.

## Auth rules

- Login/logout/restore are the auth store's own actions (`login`, `logout`, `initialize`). They call the auth service; `login` stores the tokens through the token storage file and sets the session state. Pages call these actions (for example `LoginPage`), never the service or the token file directly.
- The Axios interceptor reads the token from the token storage file, outside React. Components never read the token directly.
- `logout` clears the auth state AND resets the cart, so the next user never sees a previous cart.
- Route protection and role checks are covered in skill `routing-auth`.

## Persistence

- Do NOT use the `persist` middleware, `localStorage`, or `sessionStorage` on your own. Where the token and the cart survive a page refresh is the developer's decision.
- If a task needs persistence, STOP and ask.

## What does NOT belong in Zustand

- Anything fetched from the backend (use TanStack Query).
- Form state (use React Hook Form).
- State used by one component or one subtree, such as whether a modal is open or which tab is selected (use `useState`).
- Derived or duplicate values.

## Forbidden (never do these)

- A third store, or a "global" store for convenience, without approval.
- Copying query data into a store, or syncing a store with a query.
- `useCartStore()` or `useAuthStore()` without a selector.
- Mutating `state.items.push(...)` or assigning to state directly.
- API calls, `fetch`, or `axios` inside a store.
- Context API as a global store (skill `tech-stack`).
- `persist` middleware or browser storage without approval.

## Before you finish

End your reply with a short "State check" section:
- Which stores and selectors you used or changed
- Confirm that no server data was added to a store
- Confirm that every subscription uses a selector
- Any persistence or new-store question that needs the developer's decision
