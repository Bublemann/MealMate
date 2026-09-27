import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { errorResponse, loginResponse, mockApi, requestsTo, TEST_USER } from '@/test/api';
import type { Me } from '@/features/auth/storage';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const CODE = 'q2mXc3Jw-Invite_Code';
const EXPIRES = '2026-10-03T12:00:00Z';

/** Opens `path#code` like a tapped link: the fragment is in the real address bar. */
function openLink(path: string, code: string | null, user: Me | null = null) {
  window.history.replaceState(null, '', code === null ? path : `${path}#${code}`);
  return renderApp(path, { user });
}

function signedOut(routes: Record<string, unknown>) {
  return mockApi({
    'POST /api/auth/refresh': errorResponse(401, 'auth.session_expired'),
    ...routes,
  });
}

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('JoinScreen', () => {
  it('reads the code from the fragment, removes it from the URL and checks it', async () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    const fetchMock = signedOut({
      'POST /api/auth/codes/check': { kind: 'invite', expires_at: EXPIRES, username: null },
    });
    openLink('/join', CODE);

    expect(await screen.findByLabelText('Username')).toBeVisible();
    expect(window.location.hash).toBe('');
    expect(window.location.pathname).toBe('/join');
    expect(replaceState).toHaveBeenCalledWith(null, '', '/join');
    const [check] = requestsTo(fetchMock, 'POST /api/auth/codes/check');
    await expect(check?.json()).resolves.toEqual({ code: CODE });
    // The fragment never reaches the server in the URL (ACC-04).
    expect(fetchMock.mock.calls.every(([request]) => !request.url.includes(CODE))).toBe(true);
    expect(screen.getByText(/the invite link works until 03\/10\/2026/)).toBeVisible();
  });

  it('keeps the code for a reload of the same tab', async () => {
    signedOut({
      'POST /api/auth/codes/check': { kind: 'invite', expires_at: EXPIRES, username: null },
    });
    const first = openLink('/join', CODE);
    await screen.findByLabelText('Username');
    first.unmount();

    const fetchMock = signedOut({
      'POST /api/auth/codes/check': { kind: 'invite', expires_at: EXPIRES, username: null },
    });
    openLink('/join', null);

    expect(await screen.findByLabelText('Username')).toBeVisible();
    await expect(requestsTo(fetchMock, 'POST /api/auth/codes/check')[0]?.json()).resolves.toEqual({
      code: CODE,
    });
  });

  it('registers, preselecting the UI language, and opens Lists', async () => {
    await i18n.changeLanguage('de');
    const fetchMock = signedOut({
      'POST /api/auth/codes/check': { kind: 'invite', expires_at: EXPIRES, username: null },
      'POST /api/auth/join': () =>
        Response.json(loginResponse({ ...TEST_USER, language: 'de' }), { status: 201 }),
    });
    const { user, router } = openLink('/join', CODE);

    const username = await screen.findByLabelText('Benutzername');
    expect(screen.getByRole('combobox', { name: 'Sprache' })).toHaveValue('de');
    expect(username).toHaveAttribute('autocomplete', 'username');
    const password = screen.getByLabelText('Passwort');
    expect(password).toHaveAttribute('autocomplete', 'new-password');
    expect(password).toHaveAccessibleDescription(/Mindestens 8 Zeichen/);

    await user.type(username, 'Anna');
    expect(username).toHaveValue('anna');
    await user.type(screen.getByLabelText('Anzeigename'), ' Anna ');
    await user.type(password, 'correct horse battery');
    await user.click(screen.getByRole('button', { name: 'Konto anlegen' }));

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');
    await expect(requestsTo(fetchMock, 'POST /api/auth/join')[0]?.json()).resolves.toEqual({
      code: CODE,
      username: 'anna',
      display_name: 'Anna',
      password: 'correct horse battery',
      language: 'de',
    });
    expect(sessionStorage.length).toBe(0);
  });

  it('shows field errors next to their fields', async () => {
    signedOut({
      'POST /api/auth/codes/check': { kind: 'invite', expires_at: EXPIRES, username: null },
      'POST /api/auth/join': errorResponse(422, 'common.validation', [
        { loc: ['body', 'username'], code: 'taken' },
        { loc: ['body', 'password'], code: 'too_common' },
      ]),
    });
    const { user } = openLink('/join', CODE);

    await user.type(await screen.findByLabelText('Username'), 'anna');
    await user.type(screen.getByLabelText('Display name'), 'Anna');
    await user.type(screen.getByLabelText('Password'), 'password');
    await user.click(screen.getByRole('button', { name: 'Create account' }));

    expect(await screen.findByText('Already taken')).toBeVisible();
    expect(screen.getByLabelText('Username')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription(
      /Too common – choose something less guessable/,
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each([
    ['an unknown code', errorResponse(404, 'auth.code_invalid')],
    ['a reset code', { kind: 'reset', expires_at: EXPIRES, username: 'anna' }],
  ])('rejects %s', async (_case, answer) => {
    signedOut({ 'POST /api/auth/codes/check': answer });
    openLink('/join', CODE);

    expect(await screen.findByTestId(testIds.linkInvalid)).toHaveTextContent(
      "This link doesn't work (any more)",
    );
    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to login' })).toHaveAttribute('href', '/login');
  });

  it('rejects a link without a code without asking the server', async () => {
    const fetchMock = signedOut({});
    openLink('/join', null);

    expect(await screen.findByTestId(testIds.linkInvalid)).toBeVisible();
    expect(requestsTo(fetchMock, 'POST /api/auth/codes/check')).toHaveLength(0);
  });
});

describe('a link opened while someone is signed in', () => {
  it('asks to log out first, on the server too, before showing the join form', async () => {
    const fetchMock = mockApi({
      'POST /api/auth/codes/check': { kind: 'invite', expires_at: EXPIRES, username: null },
      'POST /api/auth/logout': null,
    });
    const { user, queryClient } = openLink('/join', CODE, TEST_USER);
    queryClient.setQueryData(['me', 'sessions'], ['cached for Anna']);
    localStorage.setItem('mm.user.something', 'x');

    expect(
      await screen.findByText('Signed in as Anna – log out first to use this link.'),
    ).toBeVisible();
    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument();
    expect(window.location.hash).toBe('');

    await user.click(screen.getByRole('button', { name: 'Log out' }));

    expect(await screen.findByLabelText('Username')).toBeVisible();
    expect(requestsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(1);
    expect(queryClient.getQueryData(['me', 'sessions'])).toBeUndefined();
    expect(localStorage.getItem('mm.user.something')).toBeNull();
    await expect(requestsTo(fetchMock, 'POST /api/auth/codes/check')[0]?.json()).resolves.toEqual({
      code: CODE,
    });
  });

  it('keeps the reset form hidden while the logout fails', async () => {
    await i18n.changeLanguage('de');
    mockApi({
      'POST /api/auth/codes/check': { kind: 'reset', expires_at: EXPIRES, username: 'ben' },
      'POST /api/auth/logout': errorResponse(500, 'common.internal'),
    });
    const { user, authSession } = openLink('/reset', 'reset-code', TEST_USER);

    await user.click(await screen.findByRole('button', { name: 'Abmelden' }));

    expect(await screen.findByRole('alert')).toBeVisible();
    expect(
      screen.getByText('Angemeldet als Anna – melde dich zuerst ab, um diesen Link zu nutzen.'),
    ).toBeVisible();
    expect(screen.queryByLabelText('Neues Passwort')).not.toBeInTheDocument();
    expect(authSession.getState().status).toBe('authenticated');
  });
});

describe('ResetScreen', () => {
  it('sets a new password for the account named by the code', async () => {
    const fetchMock = signedOut({
      'POST /api/auth/codes/check': { kind: 'reset', expires_at: EXPIRES, username: 'anna' },
      'POST /api/auth/reset': loginResponse(),
    });
    const { user, router } = openLink('/reset', 'reset-code');

    const username = await screen.findByLabelText('Username');
    expect(window.location.hash).toBe('');
    expect(username).toHaveValue('anna');
    expect(username).toHaveAttribute('readonly');
    const password = screen.getByLabelText('New password');
    expect(password).toHaveAttribute('autocomplete', 'new-password');
    await user.type(password, 'a brand new secret');
    await user.click(screen.getByRole('button', { name: 'Save password and log in' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/lists'));
    await expect(requestsTo(fetchMock, 'POST /api/auth/reset')[0]?.json()).resolves.toEqual({
      code: 'reset-code',
      password: 'a brand new secret',
    });
  });

  it('rejects an invite code', async () => {
    signedOut({
      'POST /api/auth/codes/check': { kind: 'invite', expires_at: EXPIRES, username: null },
    });
    openLink('/reset', 'invite-code');

    expect(await screen.findByTestId(testIds.linkInvalid)).toBeVisible();
  });

  it('shows the password rule the server rejected', async () => {
    signedOut({
      'POST /api/auth/codes/check': { kind: 'reset', expires_at: EXPIRES, username: 'anna' },
      'POST /api/auth/reset': errorResponse(422, 'common.validation', [
        { loc: ['body', 'password'], code: 'same_as_username' },
      ]),
    });
    const { user } = openLink('/reset', 'reset-code');

    await user.type(await screen.findByLabelText('New password'), 'annaanna');
    await user.click(screen.getByRole('button', { name: 'Save password and log in' }));

    expect(await screen.findByText('Must not be your username')).toBeVisible();
  });
});
