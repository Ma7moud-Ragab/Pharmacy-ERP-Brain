/**
 * Pharmacy ERP — Central Route Path Constants
 */

export const PATHS = {
  HOME: '/',
  LOGIN: '/login',
} as const;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

/**
 * Resolves the post-login destination from a router location state.
 * Only same-origin absolute paths are accepted to prevent open redirects.
 */
export const resolveRedirectPath = (state: unknown): string => {
  if (!isRecord(state) || !isRecord(state.from)) {
    return PATHS.HOME;
  }

  const { pathname, search, hash } = state.from;

  if (
    typeof pathname !== 'string' ||
    !pathname.startsWith('/') ||
    pathname.startsWith('//') ||
    pathname.includes('\\') ||
    pathname === PATHS.LOGIN
  ) {
    return PATHS.HOME;
  }

  const safeSearch = typeof search === 'string' ? search : '';
  const safeHash = typeof hash === 'string' ? hash : '';

  return `${pathname}${safeSearch}${safeHash}`;
};
