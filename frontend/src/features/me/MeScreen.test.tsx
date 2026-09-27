import { onlineManager } from '@tanstack/react-query';
import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LANGUAGE_STORAGE_KEY } from '@/i18n';
import {
  BEN,
  CARL,
  DEFAULT_ROUTES,
  errorResponse,
  mockApi,
  NO_COUPLE,
  requestsTo,
  TEST_ADMIN,
  TEST_USER,
  userRef,
  VERSION_INFO,
} from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

/** PATCH /api/me answers with the user updated by the request body. */
function patchMe(request: Request) {
  return request.json().then((body: object) => ({ ...TEST_USER, ...body }));
}

describe('MeScreen', () => {
  it('shows the running version and links to its exact source revision', async () => {
    const fetchMock = mockApi();
    renderApp('/me');

    expect(await screen.findByTestId(testIds.appVersion)).toHaveTextContent(VERSION_INFO.version);
    expect(requestsTo(fetchMock, 'GET /api/version')).toHaveLength(1);

    const sourceLink = screen.getByTestId(testIds.sourceLink);
    expect(sourceLink).toHaveAccessibleName(/^Source code \(AGPL-3\.0\)/);
    expect(within(sourceLink).getByText('(opens in a new tab)')).toHaveClass('sr-only');
    expect(sourceLink).toHaveAttribute('href', VERSION_INFO.source_url);
    expect(sourceLink).toHaveAttribute('target', '_blank');
    expect(sourceLink).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('credits Open Food Facts', async () => {
    mockApi();
    renderApp('/me');

    const link = await screen.findByRole('link', { name: /^Open Food Facts/ });
    expect(link).toHaveAttribute('href', 'https://world.openfoodfacts.org');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link.closest('p')).toHaveTextContent(
      /^Nutrition data: Open Food Facts\s*\(opens in a new tab\)\s*\(ODbL\)$/,
    );
  });

  it('shows a translated error when the version cannot be loaded', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    renderApp('/me');

    expect((await screen.findAllByText("Can't reach MealMate. Are you online?"))[0]).toBeVisible();
    expect(screen.queryByTestId(testIds.appVersion)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.sourceLink)).not.toBeInTheDocument();
  });

  it('says it cannot reach MealMate instead of loading forever while offline', async () => {
    onlineManager.setOnline(false);
    try {
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      renderApp('/me');

      expect(
        (await screen.findAllByText("Can't reach MealMate. Are you online?"))[0],
      ).toBeVisible();
      await waitFor(() => expect(screen.queryByText('Loading…')).not.toBeInTheDocument());
    } finally {
      onlineManager.setOnline(true);
    }
  });

  it('switches the language, remembers it on the device and saves it on the server', async () => {
    const fetchMock = mockApi({ 'PATCH /api/me': patchMe });
    const { user } = renderApp('/me');

    const select = screen.getByRole('combobox', { name: 'Language' });
    expect(select).toBe(screen.getByTestId(testIds.languageSelect));
    expect(select).toHaveValue('en');
    expect(
      within(select)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Deutsch', 'English']);

    await user.selectOptions(select, 'Deutsch');

    expect(await screen.findByRole('heading', { level: 1, name: 'Profil' })).toBeVisible();
    expect(screen.getByRole('combobox', { name: 'Sprache' })).toHaveValue('de');
    expect(screen.getByTestId(testIds.tabLists)).toHaveTextContent('Listen');
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('de');
    expect(document.documentElement.lang).toBe('de');
    await waitFor(() => expect(requestsTo(fetchMock, 'PATCH /api/me')).toHaveLength(1));
    const [patch] = requestsTo(fetchMock, 'PATCH /api/me');
    await expect(patch?.json()).resolves.toEqual({ language: 'de' });
    expect(patch?.headers.get('Authorization')).toBe('Bearer test-access-token');

    await waitFor(() => expect(screen.getByTestId(testIds.languageSelect)).toBeEnabled());
    await user.selectOptions(screen.getByTestId(testIds.languageSelect), 'English');

    expect(await screen.findByRole('heading', { level: 1, name: 'Me' })).toBeVisible();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en');
  });

  it('switches the UI to the language stored on the server', async () => {
    mockApi({ 'GET /api/me': { ...TEST_USER, language: 'de' } });
    renderApp('/me');

    expect(await screen.findByRole('heading', { level: 1, name: 'Profil' })).toBeVisible();
  });

  it('changes the display name and shows field errors', async () => {
    let taken = true;
    const fetchMock = mockApi({
      'PATCH /api/me': (request: Request) =>
        taken
          ? errorResponse(422, 'common.validation', [
              { loc: ['body', 'display_name'], code: 'taken' },
            ])
          : patchMe(request),
    });
    const { user } = renderApp('/me');

    const input = screen.getByTestId(testIds.displayNameInput);
    expect(input).toHaveValue('Anna');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    await user.clear(input);
    await user.type(input, 'Ben');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Already taken')).toBeVisible();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/Already taken/);

    taken = false;
    await user.clear(input);
    await user.type(input, 'Annie');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Saved.')).toBeVisible();
    expect(input).not.toHaveAttribute('aria-invalid');
    const last = requestsTo(fetchMock, 'PATCH /api/me').at(-1);
    await expect(last?.json()).resolves.toEqual({ display_name: 'Annie' });
  });

  it('toggles the privacy switches on the server (VIS-02)', async () => {
    const fetchMock = mockApi({ 'PATCH /api/me': patchMe });
    const { user } = renderApp('/me');

    const meals = screen.getByRole('switch', { name: 'Meals public' });
    const lists = screen.getByRole('switch', { name: 'Lists public' });
    expect(meals).toBe(screen.getByTestId(testIds.mealsPublicSwitch));
    expect(lists).toBe(screen.getByTestId(testIds.listsPublicSwitch));
    expect(meals).toBeChecked();
    expect(lists).toBeChecked();
    expect(meals).toHaveAccessibleDescription(/Everyone can see your meals/);

    await user.click(meals);

    await waitFor(() => expect(meals).not.toBeChecked());
    await waitFor(() => expect(meals).toBeEnabled());
    expect(lists).toBeChecked();
    const [patch] = requestsTo(fetchMock, 'PATCH /api/me');
    await expect(patch?.json()).resolves.toEqual({ meals_public: false });

    await user.click(lists);
    await waitFor(() => expect(lists).not.toBeChecked());
    await expect(requestsTo(fetchMock, 'PATCH /api/me')[1]?.json()).resolves.toEqual({
      lists_public: false,
    });
  });

  it('shows a failed privacy change and keeps the old state', async () => {
    mockApi({ 'PATCH /api/me': errorResponse(500, 'common.internal') });
    const { user } = renderApp('/me');

    const meals = screen.getByRole('switch', { name: 'Meals public' });
    await user.click(meals);

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeVisible();
    expect(meals).toBeChecked();
  });

  it('shows the password reset notice (ACC-10)', async () => {
    mockApi({
      'GET /api/me/security': {
        password_changed_at: '2026-09-20T10:00:00Z',
        password_reset_at: '2026-09-20T10:00:00Z',
        password_reset_by: userRef('Admin', 'a1'),
      },
    });
    renderApp('/me');

    expect(await screen.findByTestId(testIds.securityNotice)).toHaveTextContent(
      /^Your password was reset by Admin on 20\/09\/2026, \d\d:\d\d\.$/,
    );
  });

  it('changes the password and reports a wrong current password', async () => {
    let wrong = true;
    const fetchMock = mockApi({
      'POST /api/me/password': () => (wrong ? errorResponse(403, 'auth.password_incorrect') : null),
    });
    const { user } = renderApp('/me');

    await user.click(screen.getByTestId(testIds.changePasswordButton));
    const dialog = await screen.findByRole('dialog', { name: 'Change password' });
    await user.type(within(dialog).getByLabelText('Current password'), 'old-secret');
    await user.type(within(dialog).getByLabelText('New password'), 'a much better one');
    await user.click(within(dialog).getByRole('button', { name: 'Change password' }));

    expect(await within(dialog).findByText('Your current password is wrong.')).toBeVisible();

    wrong = false;
    await user.click(within(dialog).getByRole('button', { name: 'Change password' }));

    expect(
      await screen.findByText('Password changed. Your other devices have been logged out.'),
    ).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await expect(requestsTo(fetchMock, 'POST /api/me/password')[1]?.json()).resolves.toEqual({
      current_password: 'old-secret',
      new_password: 'a much better one',
    });
  });

  it('lists the sessions and logs out another device', async () => {
    const other = {
      id: 's2',
      user_agent:
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36',
      created_at: '2026-09-02T10:00:00Z',
      last_used_at: '2026-09-25T10:00:00Z',
      current: false,
    };
    const sessions = DEFAULT_ROUTES['GET /api/me/sessions'] as object[];
    const fetchMock = mockApi({
      'GET /api/me/sessions': [...sessions, other],
      'DELETE /api/me/sessions/s2': null,
    });
    const { user } = renderApp('/me');

    const list = await screen.findByTestId(testIds.sessionList);
    const rows = await within(list).findAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Safari · iPhone');
    expect(rows[0]).toHaveTextContent('This device');
    expect(within(rows[0] as HTMLElement).queryByRole('button')).not.toBeInTheDocument();

    await user.click(within(list).getByRole('button', { name: 'Log out Chrome · Mac' }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'DELETE /api/me/sessions/s2')).toHaveLength(1),
    );
  });

  it('logs out and forgets the user (SYNC-10)', async () => {
    const fetchMock = mockApi({ 'POST /api/auth/logout': null });
    localStorage.setItem('mm.user.profile', JSON.stringify(TEST_USER));
    const { user, router } = renderApp('/me');

    await user.click(screen.getByTestId(testIds.logoutButton));

    expect(await screen.findByTestId(testIds.screenLogin)).toBeVisible();
    expect(router.state.location.pathname).toBe('/login');
    expect(screen.getByTestId(testIds.loginReason)).toHaveTextContent("You're logged out.");
    expect(localStorage.getItem('mm.user.profile')).toBeNull();
    expect(requestsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(1);
  });

  it('stays logged in when the logout request fails', async () => {
    mockApi({ 'POST /api/auth/logout': () => Promise.reject(new TypeError('Failed to fetch')) });
    const { user } = renderApp('/me');

    await user.click(screen.getByTestId(testIds.logoutButton));

    expect(await screen.findByText("Can't reach MealMate. Are you online?")).toBeVisible();
    expect(screen.getByTestId(testIds.screenMe)).toBeVisible();
  });

  it('logs out on all devices after confirming', async () => {
    const fetchMock = mockApi({ 'POST /api/auth/logout-all': null });
    const { user } = renderApp('/me');

    await user.click(screen.getByTestId(testIds.logoutAllButton));
    const dialog = await screen.findByRole('alertdialog', { name: 'Log out on all devices?' });
    await user.click(within(dialog).getByRole('button', { name: 'Log out everywhere' }));

    expect(await screen.findByTestId(testIds.screenLogin)).toBeVisible();
    const [request] = requestsTo(fetchMock, 'POST /api/auth/logout-all');
    expect(request?.headers.get('Authorization')).toBe('Bearer test-access-token');
  });

  it('shows the admin entry to admins only', async () => {
    mockApi({ 'GET /api/me': TEST_ADMIN });
    renderApp('/me', { user: TEST_ADMIN });

    const entry = await screen.findByTestId(testIds.adminEntry);
    expect(within(entry).getByRole('link', { name: 'Users' })).toHaveAttribute(
      'href',
      '/me/admin/users',
    );
    expect(within(entry).getByRole('link', { name: 'Invites' })).toBeVisible();
    expect(within(entry).getByRole('link', { name: 'Categories' })).toHaveAttribute(
      'href',
      '/me/admin/categories',
    );
    expect(within(entry).getByRole('link', { name: 'Activity log' })).toBeVisible();
    expect(within(entry).getByRole('link', { name: 'System' })).toHaveAttribute(
      'href',
      '/me/admin/system',
    );
  });

  it('hides the admin entry from normal users', async () => {
    mockApi();
    renderApp('/me');

    expect(await screen.findByTestId(testIds.coupleSection)).toBeVisible();
    expect(screen.queryByTestId(testIds.adminEntry)).not.toBeInTheDocument();
  });
});

describe('CoupleSection', () => {
  it('sends a couple request to a user from the picker (CPL-01)', async () => {
    const outgoing = {
      id: 'r1',
      from_user: userRef('Anna', TEST_USER.id),
      to_user: CARL,
      created_at: '2026-09-26T10:00:00Z',
    };
    const fetchMock = mockApi({
      'POST /api/couple/requests': () => Response.json({ ...NO_COUPLE, outgoing }, { status: 201 }),
      'POST /api/couple/requests/r1/cancel': NO_COUPLE,
    });
    const { user } = renderApp('/me');

    const section = await screen.findByTestId(testIds.coupleSection);
    const picker = await within(section).findByRole('combobox', {
      name: 'Send a couple request to',
    });
    await waitFor(() => expect(picker).toBeEnabled());
    expect(
      within(picker)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Choose a person', 'Ben', 'Carl']);
    expect(within(section).getByRole('button', { name: 'Send request' })).toBeDisabled();

    await user.selectOptions(picker, 'Carl');
    await user.click(within(section).getByRole('button', { name: 'Send request' }));

    expect(
      await within(section).findByText('Request sent to Carl. Waiting for an answer.'),
    ).toBeVisible();
    await expect(requestsTo(fetchMock, 'POST /api/couple/requests')[0]?.json()).resolves.toEqual({
      user_id: CARL.id,
    });

    await user.click(within(section).getByRole('button', { name: 'Withdraw request' }));
    expect(await within(section).findByRole('combobox')).toBeVisible();
  });

  it('accepts an incoming request', async () => {
    const incoming = {
      id: 'r2',
      from_user: BEN,
      to_user: userRef('Anna', TEST_USER.id),
      created_at: '2026-09-26T10:00:00Z',
    };
    mockApi({
      'GET /api/couple': { ...NO_COUPLE, incoming: [incoming] },
      'POST /api/couple/requests/r2/accept': {
        ...NO_COUPLE,
        partner: BEN,
        since: '2026-09-26T11:00:00Z',
      },
    });
    const { user } = renderApp('/me');

    const section = await screen.findByTestId(testIds.coupleSection);
    expect(
      await within(section).findByText('Ben would like to be a couple with you.'),
    ).toBeVisible();
    expect(within(section).getByRole('button', { name: 'Decline request from Ben' })).toBeVisible();
    await user.click(within(section).getByRole('button', { name: 'Accept request from Ben' }));

    expect(await within(section).findByTestId(testIds.couplePartner)).toHaveTextContent(
      "You're a couple with Ben since 26/09/2026.",
    );
  });

  it('shows a deactivated partner and ends the couple after confirming (CPL-05, CPL-07)', async () => {
    let ended = false;
    const fetchMock = mockApi({
      'GET /api/couple': () =>
        ended ? NO_COUPLE : { ...NO_COUPLE, partner: userRef('Ben', BEN.id, true), since: null },
      'DELETE /api/couple': () => {
        ended = true;
        return null;
      },
    });
    const { user } = renderApp('/me');

    const section = await screen.findByTestId(testIds.coupleSection);
    expect(await within(section).findByTestId(testIds.couplePartner)).toHaveTextContent(
      "You're a couple with Ben (deactivated).",
    );
    await user.click(within(section).getByRole('button', { name: 'End couple' }));
    const dialog = await screen.findByRole('alertdialog', {
      name: 'End the couple with Ben (deactivated)?',
    });
    await user.click(within(dialog).getByRole('button', { name: 'End couple' }));

    expect(await within(section).findByRole('combobox')).toBeVisible();
    expect(requestsTo(fetchMock, 'DELETE /api/couple')).toHaveLength(1);
  });

  it('translates couple errors', async () => {
    mockApi({ 'POST /api/couple/requests': errorResponse(409, 'couple.target_in_couple') });
    const { user } = renderApp('/me');

    const section = await screen.findByTestId(testIds.coupleSection);
    const picker = await within(section).findByRole('combobox');
    await waitFor(() => expect(picker).toBeEnabled());
    await user.selectOptions(picker, 'Ben');
    await user.click(within(section).getByRole('button', { name: 'Send request' }));

    expect(await within(section).findByText('This person is already in a couple.')).toBeVisible();
  });
});
