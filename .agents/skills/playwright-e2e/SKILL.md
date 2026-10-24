---
name: playwright-e2e
description: Use when creating, changing, or running Playwright end-to-end tests, test ids, or the demo flow.
---

# Playwright E2E Tests

This rule is STRICT. It applies to every task that creates, changes, or runs end-to-end tests.
The frontend team owns the E2E suite as ONE unit (skill `ownership`).
Tool: Playwright only (skill `tech-stack`). Unit and component tests use Vitest and React Testing Library, never Playwright.

## The 7 laws

1. **Test like a real user, through the UI.** Click, type, and read the screen. Do not call the API to perform the action under test.
2. **Use stable selectors only** (see the selector order below). Never CSS classes, XPath, or position-based selectors.
3. **NEVER use fixed waits** (`waitForTimeout`, `sleep`). Wait for real conditions.
4. **Every test is independent.** No test depends on another test, on the run order, or on leftover data.
5. **NEVER run tests against production or real data.** The target environment comes from configuration, and the default is local or mock.
6. **NEVER weaken, skip, or delete a test to make the suite green.** Fix the cause or report it.
7. **NEVER say a test passed without running it.** If you could not run it, say so.

## Where tests and helpers live

- Follow `STRUCTURE.md` (skill `project-structure`) for the location of specs, fixtures, and helpers. Never invent a path.
- One spec file per module or per flow. Do not put unrelated flows in one big file.
- Shared pieces (config, fixtures, helpers) are shared across the suite — reuse them. Never rewrite or delete another member's spec without telling the developer.
- Check for an existing helper before writing a new one (skill `components` logic): login, add to cart, create a purchase order, and similar actions are written once and reused.
- Keep every spec and helper file under 150 lines. Split when it grows.

## Selectors (in this order)

1. **Role and accessible name:** `getByRole('button', { name: ... })`
2. **Label:** `getByLabel(...)`
3. **Visible text** for static content: `getByText(...)`
4. **`data-testid`** only when the first three are not possible.

- Test ids are kebab-case and describe purpose, not looks: `sale-checkout-button`, not `blue-btn`.
- Add `data-testid` only to frontend components. Never remove or rename an existing test id: other tests may use it.
- For shared components (design system, AI), prefer role, label, or text selectors. Only add a test id to shared code when there is no other way, and tell the developer.
- Never select by Tailwind classes, generated class names, or DOM position (`nth-child`).

## Waiting and assertions

- Use Playwright's auto-waiting and web-first assertions: `await expect(locator).toBeVisible()`, `toHaveText(...)`, `toHaveCount(...)`.
- When a step depends on a network call, wait for the response with `waitForResponse` or wait for the visible result. Do not guess a delay.
- Do not use plain `expect(await locator.isVisible())` patterns that skip auto-retry.
- Every test ends with assertions about what the user sees, not about internal state.
- Do not add retries inside a test to hide flakiness. Find the cause.

## Independence and data

- Each test creates what it needs, using unique values (for example a unique reference or name per run), and does not rely on data left by another test.
- Setup that is not the point of the test, such as being logged in, may use a saved authentication state or an API call. The flow under test still goes through the UI.
- Test users and passwords come from environment variables or fixtures. Never hardcode real credentials.
- Saved authentication files contain tokens: they must never be committed. If they are not ignored by git, tell the developer.
- Never run a full-stack test that could change shared data without asking first (skill `safe-operations`).

## Flows to cover

The developer's priority flows:
1. **Login:** valid login, invalid login, and logout (skill `routing-auth`).
2. **Role access:** only the permissions that are actually defined (skill `routing-auth`). If the permission matrix is unknown, ask. Do not invent rules to test.
3. **POS sale, end to end:** add products to the cart, complete the sale, see the confirmation, and see the cart cleared.
4. **Purchase order:** create a purchase order and see it in the purchasing list.
5. **Session expiry:** a `401` sends the user to login with the expiry message.
6. **The demo flow** (the blueprint's demo scenario): a sale is made, an insight appears on the inventory screen, a proposed action is approved, and the resulting purchase order appears in the purchasing screen. Tag it `@demo`. It depends on the Brain, so use contract fixtures or mocks until the real service is available, and say clearly which one a run used.

Tag short, fast checks `@smoke`.

## Writing a test

- Name tests as the behavior: `user can complete a sale`, not `test1`.
- One flow per test. Use `test.step` to label stages in long flows such as the demo.
- Structure: set up, act through the UI, assert on the screen.
- Use TypeScript strictly (skill `typescript-strictness`). Use the generated types for any payload you build (skill `contracts-types`).

## Configuration and files

- The base URL, environment, and credentials come from configuration and environment variables. Never hardcode a URL.
- You may edit the E2E configuration and helpers as part of the developer's suite. Adding a new Playwright plugin, reporter, or package needs approval (skill `tech-stack`).
- Do not edit CI workflows. They belong to Ali (skill `ownership`).
- Traces, screenshots, and videos are produced only on failure. Never commit them.

## Running tests

- While developing, run only the relevant spec, not the whole suite.
- Report the real result: which tests ran, which passed, which failed, and why.
- If a test fails, read the failure and fix the cause. Do not "fix" it by making the assertion weaker.
- If you cannot run the tests (no environment, no running server), say so. Do not claim the tests pass.
- Stop any dev server or process you started.

## Forbidden (never do these)

- `waitForTimeout` or any fixed delay.
- CSS class, XPath, or position selectors.
- Calling the API for the action that the test is supposed to verify.
- Tests that depend on each other or on the run order.
- Skipping (`test.skip`, `test.fixme`), deleting, or weakening a test without telling the developer.
- Editing another member's spec files.
- Editing anything outside `apps/erp-frontend/` for test purposes.
- Hardcoded URLs, credentials, or tokens.
- Running against production or real data.
- Saying a test passed when it was not run.

## Before you finish

End your reply with a short "E2E check" section:
- Which tests you created or changed
- Which tests you ran, and the real result
- Which environment they ran against (mock, fixtures, local stack)
- Any test id you added, and any selector problem you found in a shared component
