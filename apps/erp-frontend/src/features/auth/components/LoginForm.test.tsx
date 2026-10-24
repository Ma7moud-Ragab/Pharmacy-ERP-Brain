/** @vitest-environment jsdom */
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { delay, http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { cleanup, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'react-toastify';
import authTokenPair from '@contracts/fixtures/auth-token-pair.json';
import { handlers } from '../../../mocks/handlers';
import { tokenStorage } from '../../../lib/auth/tokenStorage';
import { useAuthStore } from '../../../stores/authStore';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { LoginForm } from './LoginForm';

const server = setupServer(...handlers);

beforeAll(() => server.listen());
afterEach(() => {
  cleanup();
  server.resetHandlers();
  toast.dismiss();
  tokenStorage.clearTokens();
});
afterAll(() => server.close());

beforeEach(() => {
  useAuthStore.setState({
    currentUser: null,
    isAuthenticated: false,
    isInitializing: false,
  });
});

const fillCredentials = async (
  user: ReturnType<typeof userEvent.setup>,
  password = 'password123'
) => {
  await user.type(screen.getByLabelText('Organization code'), 'PHARMAPLUS');
  await user.type(screen.getByLabelText('Username'), 'fa.pharmacist');
  await user.type(screen.getByLabelText('Password'), password);
};

describe('LoginForm', () => {
  it('renders labeled credential fields', () => {
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);

    expect(screen.getByLabelText('Organization code')).toBeDefined();
    expect(screen.getByLabelText('Username')).toBeDefined();
    expect(screen.getByLabelText('Password')).toBeDefined();
  });

  it('shows validation errors and blocks submit when fields are empty', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    renderWithProviders(<LoginForm onSuccess={onSuccess} />);

    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(
      await screen.findByText('Organization code is required')
    ).toBeDefined();
    expect(screen.getByText('Username is required')).toBeDefined();
    expect(screen.getByText('Password is required')).toBeDefined();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('signs in and notifies success for valid credentials', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    renderWithProviders(<LoginForm onSuccess={onSuccess} />);

    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Signed in successfully')).toBeDefined();
  });

  it('notifies an error for invalid credentials', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    renderWithProviders(<LoginForm onSuccess={onSuccess} />);

    await fillCredentials(user, 'invalid');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(
      await screen.findByText('Invalid organization code or credentials.')
    ).toBeDefined();
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('maps server field errors onto the matching inputs', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json(
          {
            error: {
              code: 'VALIDATION_FAILED',
              message: 'Validation failed',
              details: [{ field: 'username', issue: 'Unknown username' }],
            },
          },
          { status: 422 }
        )
      )
    );
    renderWithProviders(<LoginForm onSuccess={vi.fn()} />);

    await fillCredentials(user);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Unknown username')).toBeDefined();
  });

  it('disables the submit button while the request is in flight', async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    server.use(
      http.post('*/api/v1/auth/login', async () => {
        await delay(50);
        return HttpResponse.json(authTokenPair, { status: 200 });
      })
    );
    renderWithProviders(<LoginForm onSuccess={onSuccess} />);

    const button = screen.getByRole('button', { name: 'Sign in' });
    await fillCredentials(user);
    await user.click(button);

    await waitFor(() => expect(button.hasAttribute('disabled')).toBe(true));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });
});
