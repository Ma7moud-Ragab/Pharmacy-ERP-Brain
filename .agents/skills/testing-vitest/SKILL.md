---
name: testing-vitest
description: Use when writing, modifying, or running unit and component tests with Vitest and React Testing Library.
---

# Unit and Component Testing (Vitest + RTL)

This rule is STRICT. It applies to every unit test, hook test, and React component test.
Stack: Vitest + `@testing-library/react` + `@testing-library/user-event`. See skill `tech-stack`.
E2E testing is strictly owned by Playwright (skill `playwright-e2e`). Never use Playwright for unit/component tests, and never use Jest.

## The 6 laws

1. **Test behavior, not implementation details.** Assert on what the user sees or what functions return, not component state variables or private helpers.
2. **Co-locate tests with the code.** Unit and component tests reside next to the source file they verify as `ComponentName.test.tsx` or `hookName.test.ts`.
3. **Always wrap components in the shared test harness.** Every component using routing, queries, or themes must render via a test harness containing `QueryClientProvider` and `MemoryRouter`.
4. **Isolate state between tests.** Reset Zustand stores and clear the TanStack Query cache in `afterEach` or `beforeEach`.
5. **Simulate real user actions with `userEvent`.** Prefer `userEvent` over `fireEvent` for typing, clicking, and selecting.
6. **No flaky sleeps.** Use `waitFor`, `findByRole`, or `findByText` instead of arbitrary timeouts.

## 1. Where Tests Live

- Tests live directly alongside the file they test:
  - Component: `src/features/sales/components/SaleRow.tsx` -> `src/features/sales/components/SaleRow.test.tsx`
  - Hook: `src/features/sales/hooks/useSaleTotals.ts` -> `src/features/sales/hooks/useSaleTotals.test.ts`
  - Lib/Service: `src/lib/auth/tokenStorage.ts` -> `src/lib/auth/tokenStorage.test.ts`
- Multi-module / integration tests (auth, routing guards, contract fixtures) live in `src/test/`, like the existing ones there.
- MSW handlers and the dev worker live in `src/mocks/` (`handlers.ts`, `browser.ts`) — reuse them in tests; never create a second set.

## 2. Test Harness & Providers

Never instantiate a live network client or shared query cache in tests. Use a custom `renderWithProviders` helper — create it at `src/test/renderWithProviders.tsx` the first time a test needs providers (`STRUCTURE.md`), and tell the developer:

```tsx
import type { PropsWithChildren, ReactElement } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

interface ExtendedRenderOptions extends Omit<RenderOptions, 'queries'> {
  initialEntries?: string[];
  queryClient?: QueryClient;
}

export function renderWithProviders(
  ui: ReactElement,
  {
    initialEntries = ['/'],
    queryClient = createTestQueryClient(),
    ...renderOptions
  }: ExtendedRenderOptions = {}
) {
  function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient,
  };
}
```

## 3. Mocking Dependencies

### A. TanStack Query
- Seed query data directly into the test `queryClient` using `queryClient.setQueryData(key, mockData)` before rendering, OR use Mock Service Worker (MSW) to intercept HTTP endpoints.
- Never mock the `useQuery` hook itself with `vi.mock` unless testing a purely isolated UI branch that cannot mount a provider.

### B. Zustand Stores
- Reset store state before or after each test to avoid test contamination:
  ```ts
  import { useTestStore } from '../store/testStore.ts';

  const initialStoreState = useTestStore.getState();

  beforeEach(() => {
    useTestStore.setState(initialStoreState, true);
  });
  ```
- To test a specific scenario (e.g., cart with 5 items), seed the store state directly using `useTestStore.setState({ cartCount: 5 })`.

### C. React Router
- Pass specific route paths via `MemoryRouter`'s `initialEntries={['/sales?tab=history']}`.
- If asserting navigation, mock `useNavigate` using `vi.fn()`:
  ```ts
  const mockNavigate = vi.fn();
  vi.mock('react-router-dom', async () => {
    const actual = await vi.importActual('react-router-dom');
    return {
      ...actual,
      useNavigate: () => mockNavigate,
    };
  });
  ```

## 4. Querying and Assertions

Follow the accessible query priority order:
1. `screen.getByRole('button', { name: /save/i })`
2. `screen.getByLabelText(/email/i)`
3. `screen.getByText(/order summary/i)`
4. `screen.getByTestId('supplier-code')` (only when accessible roles do not fit)

For asynchronous elements (data loaded via queries):
```ts
const heading = await screen.findByRole('heading', { name: /suppliers/i });
expect(heading).toBeInTheDocument();
```

## Forbidden (never do these)

- Using Jest, Cypress, or Playwright for unit/component specs.
- Testing internal React state or component properties directly.
- Leaving un-reset Zustand state or dirty query caches between tests.
- Using `waitForTimeout` or arbitrary `setTimeout` delays in assertions.
- Interacting with DOM nodes using `fireEvent` when `userEvent` can be used.
- Querying elements by CSS classes, HTML tag names (`container.querySelector('div.bg-red')`), or XPath.
- Silencing failing tests with empty assertions or removing assertions to make CI green.

## Before you finish

End your reply with a short "Vitest check" section:
- Which test files were created or modified
- How TanStack Query, Zustand, and Router contexts were wrapped/mocked
- Whether tests clean up state after execution
- Confirm all tests pass without warnings
