---
name: routing-auth
description: Use when working on routes, navigation, protected routes, roles and permissions, login, logout, sessions, token storage, or 401 and 403 handling.
---

# Routing and Auth

Stack: React Router v7. It is permitted and expected to import web-specific routing components and hooks (e.g., `Link`, `NavLink`, `useNavigate`, `RouterProvider`) directly from `react-router-dom` since this is a Vite SPA.

## The 6 laws

1. **ALL routes are defined in ONE router file.** Never register routes anywhere else.
2. **Protection happens through `ProtectedRoute` and a role gate.** Never write ad-hoc "if not logged in" checks inside pages.
3. **Role checks are for UX only.** The backend is the real security. Hiding a button never replaces a backend check.
4. **Only ONE module touches the token in browser storage** (the token storage file). No other file reads or writes it.
5. **Never invent roles or permissions.** Use only the roles and rules the developer or the contract gives you.
6. **Never hardcode route path strings.** Use the central paths file.

## Where things live

| Responsibility | One file for |
| --- | --- |
| Router definition | All routes |
| Path constants | Every route path |
| `ProtectedRoute` and role gate | Route protection |
| App Shell layout (header, sidebar, `<Outlet />`) | The shared layout |
| Token storage | The only file allowed to touch browser storage |
| Auth hook used by components | `useAuth()` |
| Role to permission map | All permission logic |

Where each file goes is defined in `STRUCTURE.md` (skill `project-structure`). Read it before creating a file. Never hardcode or invent a path. Keep these responsibilities in separate files.

## Routing structure

- Use a data router with `RouterProvider` imported directly from `react-router-dom`.
- Public routes: only the login page. Everything else sits under `ProtectedRoute`.
- All authenticated pages render inside ONE `AppShell` layout route using `<Outlet />`.
- Every page is registered in the router file and added to the paths file.
- Provide a Not Found page for unknown routes.
- Provide a Not Allowed (403) page for a logged-in user without permission. This page is NOT the login page.
- Navigation uses `Link`, `NavLink`, and `useNavigate` with constants from the paths file.

## Roles and permissions

- The roles are `Admin`, `Pharmacist`, and `Cashier`, taken from the user's `roles` (typed from the contracts, skill `contracts-types`).
- ALL permission logic lives in the one permissions file as a single map (role to allowed routes/actions) and a helper such as `hasRole` / `can`.
- Pages and components call the helper through `useAuth()`. They never compare role strings themselves.
- The sidebar shows only the items the current role may open.
- **If the permission matrix is not known** (which role may open which screen or do which action), STOP and ask the developer. Do not guess.

## Session flow (fixed behavior)

**Login**
1. The login form calls the auth store's `login` action (skill `client-state`); the store calls the auth service, which stores the tokens through the token storage file.
2. On success the store sets the session (`currentUser`, `isAuthenticated`), then the app redirects to the page the user originally tried to open, or to the default home page.

**Logout**
1. Call `logout` on the auth store (it also resets the cart, skill `client-state`).
2. Remove the token through the token storage file.
3. Clear the TanStack Query cache, so the next user never sees previous data.
4. Redirect to login.

**401 from the API** (handled by the Axios response interceptor, skill `api-server-state`)
1. Do the same cleanup as logout.
2. Redirect to login with a short "session expired" message.
3. The interceptor lives outside React, so it triggers ONE handler registered at app start. It does not use `window.location` hacks.

**403 from the API**
- Show a "not allowed" message. Do NOT log the user out.

**App start**
- If a stored token exists, restore the session through the token storage file and the auth store before rendering protected routes. Show a loading state while restoring.
- If the token is expired or invalid, treat the user as logged out.
- The session context includes `runtime` (`Cloud` or `BranchLocal`). Gate screens on the declared runtime (`FRONTEND.md` §1): a route the current runtime does not own returns 404/405.

## Token storage (current decision)

- The token is stored through the token storage file ONLY. The current default is `sessionStorage` (survives a refresh, cleared when the tab closes).
- Keep the session's identity data from the auth responses too: `expires_in`, `issuer`, `audience`, `key_id`, and the user's scope (roles, `organization_id`, `branch_scope`, `branch_ids`) — the contract requires them for local JWT validation (JWKS `kid`) and scope checks.
- This is the developer's decision to change. If the team decides otherwise, only the token storage file changes. No other file may be affected.
- NEVER put the token in the URL, in query keys, in logs, or in `console.log`.
- NEVER store the password or any credentials.

## Token refresh

- The contract defines `POST /auth/refresh` with **rotation on every use**: each call returns a new refresh token, and reusing a consumed one revokes the whole token family, forcing re-login.
- The flow lives in the Axios interceptor (skill `api-server-state`): on `401`, try ONE refresh and retry the original request; if the refresh fails (`401`/`409`), run the full logout cleanup and send the user to login with the expiry message.
- Never refresh in components or hooks, and never store or log the refresh token anywhere except the token storage file.

## Forbidden (never do these)

- Other routers (TanStack Router, Next.js routing, Reach Router).
- Defining routes outside the router file.
- Auth or role checks written inline in a page (`if (!user) navigate(...)`, `user.role === 'Admin'`).
- Reading or writing `localStorage` or `sessionStorage` anywhere except the token storage file.
- Hardcoded path strings like `navigate('/sales')`.
- Using login redirect as the response to "not allowed". That is the 403 page.
- Treating UI hiding as security.
- Inventing a role, a permission, or a refresh flow.
- Leaving the old user's data in the query cache after logout.

## Before you finish

End your reply with a short "Routing check" section:
- Routes added or changed, and the paths added to the paths file
- Which roles can access them, and where this is defined in the permissions file
- Confirm that no token handling exists outside the token storage file and the interceptor
- Any permission or auth decision that needs the developer
