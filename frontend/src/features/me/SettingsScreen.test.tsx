import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  BEN,
  CARL,
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

/** The addresses of the Settings tab's rows, in order. */
function rowAddresses() {
  const settings = screen.getByTestId(testIds.screenMe);
  return within(settings)
    .getAllByRole('link')
    .map((link) => link.getAttribute('href'));
}

describe('SettingsScreen', () => {
  it('shows its headline, then the rows in their groups, Abmelden last (UI-07, D-45)', async () => {
    mockApi();
    renderApp('/me');

    const settings = await screen.findByTestId(testIds.screenMe);
    const headline = within(settings).getByRole('heading', { level: 1, name: 'Settings' });
    expect(screen.getAllByRole('heading', { level: 1 })).toEqual([headline]);
    expect(settings.firstElementChild).toBe(headline);
    expect(screen.queryByTestId(testIds.pinnedBlock)).not.toBeInTheDocument();

    expect(rowAddresses()).toEqual([
      '/me/profile',
      '/me/privacy',
      '/me/couple',
      '/me/security',
      '/me/recurring',
      '/me/about',
    ]);
    expect(within(settings).getByRole('link', { name: /^Profile/ })).toHaveAttribute(
      'href',
      '/me/profile',
    );
    expect(within(settings).getByRole('link', { name: /^Privacy/ })).toBeVisible();
    expect(within(settings).getByRole('link', { name: /^Couple/ })).toBeVisible();
    expect(within(settings).getByRole('link', { name: /^Security/ })).toBeVisible();
    expect(within(settings).getByRole('link', { name: /^Recurring items/ })).toBeVisible();
    expect(within(settings).getByRole('link', { name: /^About MealMate/ })).toBeVisible();
    // Abmelden is a button, not a link, and comes last.
    const logout = screen.getByTestId(testIds.logoutButton);
    expect(logout).toBe(within(settings).getByRole('button', { name: 'Log out' }));
    expect(settings.lastElementChild).toContainElement(logout);
    // Only admins get the Verwaltung group (ADM-01).
    expect(screen.queryByTestId(testIds.adminEntry)).not.toBeInTheDocument();
    expect(within(settings).queryByRole('heading', { name: 'Administration' })).toBeNull();
  });

  it('shows admins the Verwaltung group between their own rows and About (ADM-01)', async () => {
    mockApi({ 'GET /api/me': TEST_ADMIN });
    renderApp('/me', { user: TEST_ADMIN });

    const group = await screen.findByTestId(testIds.adminEntry);
    expect(within(group).getByRole('heading', { level: 2, name: 'Administration' })).toBeVisible();
    expect(
      within(group)
        .getAllByRole('link')
        .map((link) => [link.textContent?.trim(), link.getAttribute('href')]),
    ).toEqual([
      ['Users', '/me/admin/users'],
      ['Invites', '/me/admin/invites'],
      ['Categories', '/me/admin/categories'],
      ['Activity log', '/me/admin/events'],
      ['System', '/me/admin/system'],
    ]);
    expect(rowAddresses()).toEqual([
      '/me/profile',
      '/me/privacy',
      '/me/couple',
      '/me/security',
      '/me/recurring',
      '/me/admin/users',
      '/me/admin/invites',
      '/me/admin/categories',
      '/me/admin/events',
      '/me/admin/system',
      '/me/about',
    ]);
  });

  const PAGES = [
    { row: /^Profile/, path: '/me/profile', title: 'Profile', testId: testIds.screenProfile },
    { row: /^Privacy/, path: '/me/privacy', title: 'Privacy', testId: testIds.screenPrivacy },
    { row: /^Couple/, path: '/me/couple', title: 'Couple', testId: testIds.screenCouple },
    { row: /^Security/, path: '/me/security', title: 'Security', testId: testIds.screenSecurity },
    {
      row: /^Recurring items/,
      path: '/me/recurring',
      title: 'Recurring items',
      testId: testIds.screenRecurring,
    },
    {
      row: /^About MealMate/,
      path: '/me/about',
      title: 'About MealMate',
      testId: testIds.screenAbout,
    },
  ];

  it.each(PAGES)(
    'opens $path from its row, a detail screen with the strip back to Settings (D-45, D-46)',
    async ({ row, path, title, testId }) => {
      mockApi();
      const { router, user } = renderApp('/me');

      await user.click(await screen.findByRole('link', { name: row }));

      expect(router.state.location.pathname).toBe(path);
      const page = await screen.findByTestId(testId);
      expect(screen.getByRole('region', { name: title })).toBe(page);
      // The strip first, then the title, scrolling with the page.
      const strip = within(page).getByTestId(testIds.detailStrip);
      const heading = within(page).getByRole('heading', { level: 1, name: title });
      expect(screen.getAllByRole('heading', { level: 1 })).toEqual([heading]);
      expect(page.firstElementChild).toBe(strip);
      expect(strip.nextElementSibling).toBe(heading);
      // "‹ Einstellungen" and no ⋯ menu: these pages have no actions.
      const back = within(strip).getByTestId(testIds.backLink);
      expect(within(strip).getAllByRole('link')).toEqual([back]);
      expect(within(strip).queryByRole('button')).not.toBeInTheDocument();
      expect(back).toHaveAccessibleName('Settings');

      await user.click(back);
      expect(await screen.findByTestId(testIds.screenMe)).toBeVisible();
      expect(router.state.location.pathname).toBe('/me');
    },
  );

  it.each(PAGES)('keeps $path on a reload', async ({ path, testId }) => {
    mockApi();
    const { router } = renderApp(path);

    expect(await screen.findByTestId(testId)).toBeVisible();
    expect(router.state.location.pathname).toBe(path);
  });

  it('sends an unknown address under /me/ to Lists', async () => {
    mockApi();
    const { router } = renderApp('/me/nope');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    await waitFor(() => expect(router.state.location.pathname).toBe('/lists'));
  });

  it('switches the UI to the language stored on the server', async () => {
    mockApi({ 'GET /api/me': { ...TEST_USER, language: 'de' } });
    renderApp('/me');

    expect(await screen.findByRole('heading', { level: 1, name: 'Einstellungen' })).toBeVisible();
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
});

/** An incoming couple request from `from`. */
function requestFrom(from: ReturnType<typeof userRef>, id = `r-${from.id}`) {
  return {
    id,
    from_user: from,
    to_user: userRef('Anna', TEST_USER.id),
    created_at: '2026-09-26T10:00:00Z',
  };
}

/** The Settings row whose accessible name starts with `label`. */
function row(label: string) {
  return screen.getByRole('link', { name: new RegExp(`^${label}`) });
}

describe('SettingsScreen row values (D-45)', () => {
  it('shows the display name, refreshed as the tab opens, and the version', async () => {
    const fetchMock = mockApi({ 'GET /api/me': { ...TEST_USER, display_name: 'Annie' } });
    renderApp('/me');

    await waitFor(() => expect(row('Profile')).toHaveAccessibleName('Profile Annie'));
    expect(requestsTo(fetchMock, 'GET /api/me')).toHaveLength(1);
    await waitFor(() =>
      expect(row('About MealMate')).toHaveAccessibleName(`About MealMate ${VERSION_INFO.version}`),
    );
    // Without a partner or a request, Paar has no value; nor have these rows.
    expect(row('Couple')).toHaveAccessibleName('Couple');
    expect(row('Privacy')).toHaveAccessibleName('Privacy');
    expect(row('Security')).toHaveAccessibleName('Security');
  });

  it('shows no value on the Verwaltung rows', async () => {
    mockApi({ 'GET /api/me': TEST_ADMIN });
    renderApp('/me', { user: TEST_ADMIN });

    const group = await screen.findByTestId(testIds.adminEntry);
    const names = ['Users', 'Invites', 'Categories', 'Activity log', 'System'];
    const links = within(group).getAllByRole('link');
    expect(links).toHaveLength(names.length);
    links.forEach((link, index) => expect(link).toHaveAccessibleName(names[index]));
  });

  it('shows the partner on Paar, marked when deactivated (ADM-02)', async () => {
    let partner = BEN;
    mockApi({
      'GET /api/couple': () => ({ ...NO_COUPLE, partner, since: '2026-09-26T11:00:00Z' }),
    });
    const first = renderApp('/me');

    await waitFor(() => expect(row('Couple')).toHaveAccessibleName('Couple Ben'));
    first.unmount();

    partner = userRef('Ben', BEN.id, true);
    renderApp('/me');
    await waitFor(() => expect(row('Couple')).toHaveAccessibleName('Couple Ben (deactivated)'));
  });

  it('shows waiting couple requests on Paar, one or several (D-51)', async () => {
    let incoming = [requestFrom(BEN)];
    mockApi({ 'GET /api/couple': () => ({ ...NO_COUPLE, incoming }) });
    const first = renderApp('/me');

    await waitFor(() => expect(row('Couple')).toHaveAccessibleName('Couple 1 request'));
    first.unmount();

    incoming = [requestFrom(BEN), requestFrom(CARL)];
    renderApp('/me');
    await waitFor(() => expect(row('Couple')).toHaveAccessibleName('Couple 2 requests'));
  });

  it('leaves a row without its value, but tappable, when the value fails to load', async () => {
    const fetchMock = mockApi({
      'GET /api/couple': errorResponse(500, 'common.internal'),
      'GET /api/version': errorResponse(500, 'common.internal'),
    });
    const { router, user } = renderApp('/me');

    const settings = await screen.findByTestId(testIds.screenMe);
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/version')).toHaveLength(1));
    expect(row('Couple')).toHaveAccessibleName('Couple');
    expect(row('About MealMate')).toHaveAccessibleName('About MealMate');
    expect(within(settings).queryByRole('alert')).not.toBeInTheDocument();
    expect(within(settings).queryByText('Something went wrong. Please try again.')).toBeNull();

    await user.click(row('About MealMate'));
    expect(router.state.location.pathname).toBe('/me/about');
  });
});
