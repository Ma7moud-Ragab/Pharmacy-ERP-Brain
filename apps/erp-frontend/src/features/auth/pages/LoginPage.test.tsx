/** @vitest-environment jsdom */
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from 'vitest';
import { setupServer } from 'msw/node';
import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { toast } from 'react-toastify';
import { handlers } from '../../../mocks/handlers';
import { tokenStorage } from '../../../lib/auth/tokenStorage';
import { PublicOnlyRoute } from '../../../routes/PublicOnlyRoute';
import { useAuthStore } from '../../../stores/authStore';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { LoginPage } from './LoginPage';

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

const signIn = async () => {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Organization code'), 'PHARMAPLUS');
  await user.type(screen.getByLabelText('Username'), 'fa.pharmacist');
  await user.type(screen.getByLabelText('Password'), 'password123');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
};

describe('LoginPage', () => {
  it('renders the sign-in screen', () => {
    renderWithProviders(<LoginPage />, { initialEntries: ['/login'] });

    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeDefined();
  });

  it('redirects to the originally requested route after sign in', async () => {
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/inventory" element={<div>Inventory Target</div>} />
      </Routes>,
      {
        initialEntries: [
          { pathname: '/login', state: { from: { pathname: '/inventory' } } },
        ],
      }
    );

    await signIn();

    expect(await screen.findByText('Inventory Target')).toBeDefined();
  });

  it('redirects to home when no original route was requested', async () => {
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Home Target</div>} />
      </Routes>,
      { initialEntries: ['/login'] }
    );

    await signIn();

    expect(await screen.findByText('Home Target')).toBeDefined();
  });
});

describe('PublicOnlyRoute', () => {
  it('renders the login screen for unauthenticated users', () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <div>Login Content</div>
            </PublicOnlyRoute>
          }
        />
      </Routes>,
      { initialEntries: ['/login'] }
    );

    expect(screen.getByText('Login Content')).toBeDefined();
  });

  it('redirects authenticated users to the resolved destination', () => {
    useAuthStore.setState({ isAuthenticated: true });

    renderWithProviders(
      <Routes>
        <Route
          path="/login"
          element={
            <PublicOnlyRoute>
              <div>Login Content</div>
            </PublicOnlyRoute>
          }
        />
        <Route path="/inventory" element={<div>Inventory Target</div>} />
      </Routes>,
      {
        initialEntries: [
          { pathname: '/login', state: { from: { pathname: '/inventory' } } },
        ],
      }
    );

    expect(screen.getByText('Inventory Target')).toBeDefined();
  });
});
