import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  errorResponse,
  loginResponse,
  mockApi,
  NO_COUPLE,
  requestsTo,
  TEST_USER,
  VERSION_INFO,
} from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { PROFILE_STORAGE_KEY } from './storage';

describe('route guard', () => {
  it('sends a signed-out user to the login screen', async () => {
    mockApi({ 'POST /api/auth/refresh': errorResponse(401, 'auth.session_expired') });
    const { router } = renderApp('/lists', { user: null });

    expect(await screen.findByTestId(testIds.screenLogin)).toBeVisible();
    expect(router.state.location.pathname).toBe('/login');
    expect(screen.queryByTestId(testIds.loginReason)).not.toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main navigation' })).not.toBeInTheDocument();
  });

  it('shows the app after a successful start-up refresh', async () => {
    mockApi({ 'POST /api/auth/refresh': loginResponse() });
    renderApp('/lists', { user: null });

    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
  });

  it('offers to try again when MealMate is unreachable at start', async () => {
    let reachable = false;
    mockApi({
      'POST /api/auth/refresh': () =>
        reachable ? loginResponse() : Promise.reject(new TypeError('Failed to fetch')),
    });
    const { user } = renderApp('/lists', { user: null });

    expect(await screen.findByRole('heading', { name: "Can't reach MealMate" })).toBeVisible();
    reachable = true;
    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
  });

  it('keeps admins-only screens from normal users', async () => {
    mockApi();
    const { router } = renderApp('/me/admin/users');

    expect(await screen.findByTestId(testIds.screenMe)).toBeVisible();
    expect(router.state.location.pathname).toBe('/me');
  });
});

describe('LoginScreen', () => {
  it('logs in and returns to the page that was asked for', async () => {
    const fetchMock = mockApi({
      'POST /api/auth/refresh': errorResponse(401, 'auth.session_expired'),
      'POST /api/auth/login': loginResponse(),
      'GET /api/version': VERSION_INFO,
    });
    const { user, router } = renderApp('/me', { user: null });

    await screen.findByTestId(testIds.screenLogin);
    const username = screen.getByLabelText('Username');
    const password = screen.getByLabelText('Password');
    expect(username).toHaveAttribute('autocomplete', 'username');
    expect(username).toHaveAttribute('autocapitalize', 'none');
    expect(password).toHaveAttribute('autocomplete', 'current-password');
    await user.type(username, ' Anna ');
    await user.type(password, 'secret password');
    await user.click(screen.getByRole('button', { name: 'Log in' }));

    expect(await screen.findByTestId(testIds.screenMe)).toBeVisible();
    expect(router.state.location.pathname).toBe('/me');
    await expect(requestsTo(fetchMock, 'POST /api/auth/login')[0]?.json()).resolves.toEqual({
      username: 'anna',
      password: 'secret password',
    });
    expect(localStorage.getItem(PROFILE_STORAGE_KEY)).not.toBeNull();
  });

  it.each([
    ['auth.invalid_credentials', 401, 'Username or password is wrong.'],
    [
      'auth.account_deactivated',
      403,
      'Your account has been deactivated. Please contact your admin.',
    ],
    ['common.rate_limited', 429, 'Too many attempts. Please wait a moment.'],
  ])('translates %s', async (code, status, message) => {
    mockApi({
      'POST /api/auth/refresh': errorResponse(401, 'auth.session_expired'),
      'POST /api/auth/login': errorResponse(status, code),
    });
    const { user } = renderApp('/login', { user: null });

    await user.type(await screen.findByLabelText('Username'), 'anna');
    await user.type(screen.getByLabelText('Password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Log in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.getByTestId(testIds.screenLogin)).toBeVisible();
  });

  it('asks for one login in the Home Screen app when the fork was refused', async () => {
    mockApi({ 'POST /api/auth/refresh': errorResponse(401, 'auth.login_required') });
    renderApp('/lists', { user: null });

    expect(await screen.findByTestId(testIds.loginReason)).toHaveTextContent(
      'Please log in once in the Home Screen app.',
    );
  });

  it('sends a signed-in user on to Lists', async () => {
    mockApi();
    const { router } = renderApp('/login');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');
  });
});

describe('session revoked while in use (SYNC-10)', () => {
  it('drops cached data and user storage and shows why', async () => {
    let revoked = false;
    mockApi({
      'GET /api/couple': () => (revoked ? errorResponse(401, 'auth.session_revoked') : NO_COUPLE),
    });
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(TEST_USER));
    const { queryClient, router } = renderApp('/me');
    await screen.findByTestId(testIds.appVersion);
    expect(queryClient.getQueryData(['version'])).toEqual(VERSION_INFO);

    revoked = true;
    await queryClient.refetchQueries({ queryKey: ['couple'] });

    expect(await screen.findByTestId(testIds.loginReason)).toHaveTextContent(
      "You've been logged out on this device.",
    );
    expect(router.state.location.pathname).toBe('/login');
    expect(localStorage.getItem(PROFILE_STORAGE_KEY)).toBeNull();
    await waitFor(() => expect(queryClient.getQueryData(['version'])).toBeUndefined());
  });
});
