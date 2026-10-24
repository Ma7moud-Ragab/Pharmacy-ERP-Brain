import { describe, expect, it } from 'vitest';
import { PATHS, resolveRedirectPath } from './paths';

describe('resolveRedirectPath', () => {
  it('returns the requested path with its search and hash', () => {
    expect(
      resolveRedirectPath({
        from: { pathname: '/inventory', search: '?page=2', hash: '#row' },
      })
    ).toBe('/inventory?page=2#row');
  });

  it('falls back to home for missing or malformed state', () => {
    expect(resolveRedirectPath(undefined)).toBe(PATHS.HOME);
    expect(resolveRedirectPath({ from: { pathname: 'inventory' } })).toBe(
      PATHS.HOME
    );
    expect(resolveRedirectPath({ from: { pathname: 42 } })).toBe(PATHS.HOME);
  });

  it('rejects protocol-relative and login destinations', () => {
    expect(resolveRedirectPath({ from: { pathname: '//evil.example' } })).toBe(
      PATHS.HOME
    );
    expect(resolveRedirectPath({ from: { pathname: '/\\evil.example' } })).toBe(
      PATHS.HOME
    );
    expect(resolveRedirectPath({ from: { pathname: PATHS.LOGIN } })).toBe(
      PATHS.HOME
    );
  });
});
