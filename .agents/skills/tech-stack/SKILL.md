---
name: tech-stack
description: Use when choosing a library, adding or upgrading a dependency, changing build or config files, or writing syntax that depends on a library (react-router, TanStack Query, Tailwind, Zod, Radix, Vitest).
---

# Tech Stack Lock

This rule is STRICT. The frontend uses the stack below and NOTHING else.
If a task seems to need something outside this stack, you STOP and ask. You never decide it yourself.

## The 3 laws

1. **Use only the approved stack.** Every need must be solved with a library from the approved list.
2. **NEVER install, add, remove, or upgrade a dependency on your own.** Not for convenience, not "just a small helper".
3. **NEVER replace an approved library with an alternative**, even if you think the alternative is better.

## Approved stack

| Library | Use it for | Never use it for |
| --- | --- | --- |
| **Vite + React** | The app, components, dev server, build | Anything that needs server-side rendering |
| **TypeScript** | All code, strict typing | Plain `.js` / `.jsx` files |
| **react-router / react-router-dom** | Routing, App Shell, navigation, Protected Routes | Any other router or Next.js routing |
| **Axios** | The ONE shared HTTP client, with an interceptor that attaches the JWT | Creating extra Axios instances in components; raw `fetch` |
| **@tanstack/react-query (v5)** | ALL server data: fetching, caching, mutations, background refresh | Local UI state |
| **Zustand** | Local global state only: the POS cart and the logged-in user state | Server data (that belongs to TanStack Query) |
| **Tailwind CSS** | All styling, with utility classes inside TSX | Separate CSS files, CSS-in-JS, inline `style` objects for things Tailwind can do |
| **json-schema-to-typescript** | Generating types from the JSON Schema files in the repo-root `contracts/` (entity shapes like Product, Sale) | Hand-writing types for shapes that exist in the contracts |
| **openapi-typescript** | Generating endpoint types (paths, request and response bodies, parameters) from the OpenAPI specs in the repo-root `contracts/` | Hand-writing endpoint request/response types |
| **React Hook Form** | All forms (POS, purchase orders, supplier and product forms) | Managing form state manually with many `useState` calls |
| **Zod** | Form and input validation schemas, used with React Hook Form | Re-defining shapes that already exist as generated contract types |
| **Radix UI** | Accessible unstyled primitives (dialog/modal, dropdown, select, tabs, tooltip), styled with Tailwind | Replacing a primitive that already exists in the generic UI components |
| **lucide-react** | All icons | Any other icon library |
| **MSW (Mock Service Worker)** | The dev mock server (`src/mocks/`) and HTTP interception in tests | Calling real backends from tests; inventing another mocking library |
| **Vitest + React Testing Library** | Unit and component tests | End-to-end tests |
| **Playwright** | End-to-end tests | Unit or component tests |

## Version-aware syntax (check before writing code)

Always match the version installed in `package.json`. Do not write syntax from memory of an older version.
- **react-router:** It is permitted and expected to import web-specific routing components and hooks (e.g., `Link`, `NavLink`, `useNavigate`, `RouterProvider`) directly from `react-router-dom` since this is a Vite SPA.
- **TanStack Query v5:** use the object form (`useQuery({ queryKey, queryFn })`), `gcTime` (not `cacheTime`), and `isPending` (not `isLoading` for the initial load).
- **Tailwind:** check the installed major version first. Do not add a `tailwind.config.js` or v3-style setup to a project that uses a newer setup.
- If you are not sure about an API of an installed library, check its documentation or its installed types instead of guessing.

## Forbidden (never use, never suggest installing)

- **Next.js anything:** `next/link`, `next/image`, `next/navigation`, `"use client"`, `getServerSideProps`, App Router conventions, Server Components.
- **Other routers:** TanStack Router, Reach Router, or any router other than React Router.
- **Other state libraries:** Redux, Redux Toolkit, MobX, Recoil, Jotai, Context API as a global store.
- **Other data fetching:** raw `fetch`, `XMLHttpRequest`, SWR, `ky`, `superagent`, or `useEffect` + fetch patterns.
- **Other styling:** styled-components, Emotion, SCSS/Sass, CSS Modules, Bootstrap, and any CSS framework other than Tailwind.
- **Other form or validation libraries:** Formik, Yup, Joi.
- **Other icon libraries:** react-icons, Font Awesome, Material Icons.
- **Any styled UI component library** (MUI, Ant Design, Chakra, Mantine, shadcn/ui, and similar) unless the developer approves it. Radix UI primitives are allowed.
- **Other test tools:** Jest (use Vitest), Cypress, Selenium, Puppeteer.

## Files you must not change without asking

Changing these counts as changing the stack:
- `package.json` and the lock file
- `vite.config.*` (this includes the Vitest setup)
- `tsconfig*.json`
- Tailwind and PostCSS configuration
- ESLint / Prettier configuration
- The type-generation scripts setup

Do not run `npm install`, `npm uninstall`, `pnpm add`, `yarn add`, or any package-manager command that changes dependencies. Use the project's existing package manager only (check which lock file exists). Never mix package managers.

## Generated types

- Files generated from the repo-root `contracts/` are NEVER edited by hand. If a type is wrong or missing, tell the developer; the fix belongs in the contract, not in the generated file.
- Use `json-schema-to-typescript` output for entity shapes and `openapi-typescript` output for endpoint shapes. Do not create a second hand-written copy of either.
- Zod schemas are for form input validation only. Do not use them to re-declare API response types.

## What to do when the stack does not cover a need

1. Check first: can it be done with the approved libraries or with plain React / TypeScript? If yes, do that.
2. If not, STOP. Do not install anything and do not write code that depends on the missing library.
3. Ask the developer in this format:

> **Need:** what the task requires
> **Why the approved stack is not enough:** one line
> **Option:** the library or approach you suggest, and why
> **Impact:** what it adds (new dependency, config change, bundle size)
> Do you approve? (yes / no)

4. Proceed only after an explicit "yes". If the answer is "no", solve it within the approved stack or explain what cannot be done.

## Before you finish

End your reply with a short "Stack check" section:
- Confirm that you used only approved libraries.
- List any dependency or config file you changed (it should be "none" unless the developer approved it).
- Mention any need you found that the stack does not cover.
