import type { ComponentProps, ReactElement, ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ToastHost } from '../components/ui/ToastHost';

type MemoryRouterProps = ComponentProps<typeof MemoryRouter>;
type InitialEntry = NonNullable<MemoryRouterProps['initialEntries']>[number];

interface ProviderOptions extends Omit<RenderOptions, 'wrapper'> {
  initialEntries?: InitialEntry[];
}

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

export function renderWithProviders(
  ui: ReactElement,
  { initialEntries = ['/'], ...renderOptions }: ProviderOptions = {}
) {
  const queryClient = createTestQueryClient();

  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      <ToastHost />
    </QueryClientProvider>
  );

  return {
    queryClient,
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  };
}
