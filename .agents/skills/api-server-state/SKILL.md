---
name: api-server-state
description: Use when reading or writing backend data: the Axios client, API functions, TanStack Query hooks, query keys, mutations, and loading, error, and empty states.
---

# API and Server State

This rule is STRICT. It applies to every task that reads or writes data from the backend.
Stack: Axios (the network client) + TanStack Query v5 (all server data). See skill `tech-stack`.

## The 5 laws

1. **ONE shared Axios instance for the whole app.** Never create another one.
2. **Components NEVER call the API.** Not Axios, not `fetch`, not an API function. Components only use hooks.
3. **ALL server data goes through TanStack Query.** Reads use `useQuery`, writes use `useMutation`.
4. **Server data NEVER goes into Zustand or into `useState`.** TanStack Query is the only owner of server data.
5. **NEVER use `useEffect` + fetch** (or Axios) to load data.

## The 3 layers (each in its own place)

| Layer | Job |
| --- | --- |
| **Client** | The single Axios instance, base URL, interceptors |
| **API functions** | One typed async function per endpoint. No React inside. |
| **Hooks** | `useQuery` / `useMutation` hooks and the query keys. This is the ONLY layer components touch. |

Flow: `Component -> hook -> API function -> Axios client -> backend`. Never skip a layer.
Where each file goes is defined in `STRUCTURE.md` (skill `project-structure`). Read it before creating a file. Never hardcode or invent a path. Keep the three layers in separate files.

## 1. The Axios client

- Create it ONCE, in the API client file defined in `STRUCTURE.md`.
- The base URL comes from the environment (`import.meta.env.VITE_API_BASE_URL`). NEVER hardcode a URL anywhere. Switching between the mock server and the real backend must be an environment change only.
- **Request interceptor:** attaches the JWT as `Authorization: Bearer <token>`, reading the token from the token storage file (`lib/auth/tokenStorage.ts`). This is the ONLY place the token is attached. Components and API functions never touch the token.
- **Response interceptor:** handles errors in one place.
  - `401`: clear the auth state and send the user to login (follow skill `routing-auth` for the exact behavior).
  - Every error is converted to ONE normalized error shape that matches the backend error contract: `code`, `message`, `details`, `trace_id`.
- Do not add new global behavior to the client (retry logic, logging, extra headers) without asking the developer.
- If a different backend base URL is needed (for example the Brain API), STOP and ask. Do not create a second instance on your own.

## 2. API functions

- One function per endpoint, named by action (`getSales`, `getSaleById`, `createSale`).
- Parameters and return values use the types generated from the repo-root `contracts/` (skill `tech-stack`). No `any`. No hand-written copy of a contract type.
- They return the data (`response.data`), not the Axios response.
- They contain no React code, no state, no toasts, and no navigation.

## 3. Query keys

- Keys are arrays, built ONLY by a key factory per module. Never write inline keys inside components or hooks.

```ts
export const salesKeys = {
  all: ['sales'] as const,
  lists: () => [...salesKeys.all, 'list'] as const,
  list: (filters: SaleFilters) => [...salesKeys.lists(), filters] as const,
  detail: (id: string) => [...salesKeys.all, 'detail', id] as const,
}
```

- Same data = same key everywhere. Different filters = different key.

## 4. Query hooks (reads)

- One hook per read: `useSales(filters)`, `useSale(id)`. Use the TanStack Query v5 object form.
- Every screen that uses a query handles ALL states: `isPending` (loading), `isError` (error), empty data, and success. No screen shows a blank area while loading. Follow `DESIGN.md` for how each state looks.
- Do not copy query data into `useState` to "sync" it. Use the data directly, or derive it with `select`.
- Do not set custom `staleTime`, `retry`, or refetch options per hook unless there is a clear reason. Defaults live in ONE place: the single `QueryClient` setup file (its location is in `STRUCTURE.md`). Do not retry on `4xx` errors.
- Use `enabled` when a query depends on a value that may not exist yet. Never fire a request with an `undefined` id.
- List endpoints return `PagedResult<T>` (`{ items, nextCursor }`): follow the opaque `nextCursor` for the next page. Never invent offset/page numbers.

## 5. Mutation hooks (writes)

- One hook per write: `useCreateSale`, `useCreatePurchaseOrder`. Use `useMutation`.
- On success, invalidate every query key the write affects (for example, a new sale invalidates the sales lists). Use the key factory, not strings.
- Disable the submit button while `isPending`, to prevent double submission. A double click must never create two sales or two purchase orders.
- Show the error to the user from the normalized error `message`. For unexpected errors, also show the `trace_id` so the team can find it in the logs.
- **Every mutation carries an `Idempotency-Key` header (16–100 characters) — the contract requires it on all mutations.** Same key + same payload replays the stored response safely; same key + a different payload → `409 IDEMPOTENCY_MISMATCH`. Keep the same key when retrying a failed write.
- Normalized error `code` handling: `OUT_OF_STOCK` (409) → show the per-line shortages from `details`; `422` → field errors go to the form (skill `forms-validation`); `401` → the single refresh/logout flow (skill `routing-auth`).
- Never swallow errors with an empty `catch`.
- Do not use optimistic updates unless the developer asks for them.

## 6. What belongs in Zustand (not server data)

Only the POS cart and the logged-in user state (skill `client-state`). If you are about to put anything fetched from the backend into a store, STOP: it belongs in TanStack Query.

## Forbidden (never do these)

- `fetch(...)`, `XMLHttpRequest`, or `axios.create(...)` inside a component or a hook.
- Importing Axios or an API function directly in a component.
- `useEffect` that loads data, with or without `useState`.
- Hardcoded URLs, hardcoded tokens, or reading the token anywhere except the request interceptor.
- Inline query keys such as `useQuery({ queryKey: ['sales'] })` outside a key factory.
- Storing fetched data in Zustand or `useState`.
- Hardcoded fake data inside components to "wait for the backend". Use the mock server through the environment URL.
- Responses typed as `any` or typed with a hand-written copy of a contract type.

## Before you finish

End your reply with a short "API check" section:
- Which endpoints you used, and the API functions and hooks you created or reused (check for existing ones first, per skill `components`)
- Which query keys you invalidated after writes
- Confirm that loading, error, and empty states are handled
- Confirm that no component calls the API directly
