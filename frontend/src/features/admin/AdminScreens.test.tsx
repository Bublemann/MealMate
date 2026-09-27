import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { errorResponse, mockApi, requestsTo, TEST_ADMIN, userRef } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import type { AdminEvent, AdminUser, Invite } from './api';

const ADMIN_REF = userRef('Admin', TEST_ADMIN.id);

const USERS: AdminUser[] = [
  {
    id: TEST_ADMIN.id,
    username: 'admin',
    display_name: 'Admin',
    role: 'admin',
    is_active: true,
    created_at: '2026-09-01T10:00:00Z',
    last_seen_at: '2026-09-26T10:00:00Z',
  },
  {
    id: 'u-ben',
    username: 'ben',
    display_name: 'Ben',
    role: 'user',
    is_active: true,
    created_at: '2026-09-02T10:00:00Z',
    last_seen_at: null,
  },
  {
    id: 'u-carl',
    username: 'carl',
    display_name: 'Carl',
    role: 'user',
    is_active: false,
    created_at: '2026-09-03T10:00:00Z',
    last_seen_at: '2026-09-10T10:00:00Z',
  },
];

function renderAdmin(path: string, routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    'GET /api/me': TEST_ADMIN,
    'GET /api/admin/users': USERS,
    ...routes,
  });
  return { fetchMock, ...renderApp(path, { user: TEST_ADMIN }) };
}

function userCard(name: string): HTMLElement {
  const list = screen.getByTestId(testIds.adminUserList);
  const heading = within(list).getByRole('heading', { name: new RegExp(`^${name}`) });
  return heading.closest('li') as HTMLElement;
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'share');
});

describe('AdminUsersScreen', () => {
  it('lists the users with role and status, without actions on oneself', async () => {
    renderAdmin('/me/admin');

    expect(await screen.findByTestId(testIds.screenAdminUsers)).toBeVisible();
    await screen.findByTestId(testIds.adminUserList);
    const nav = screen.getByRole('navigation', { name: 'Administration' });
    expect(within(nav).getByRole('link', { name: 'Users' })).toHaveAttribute(
      'aria-current',
      'page',
    );

    const admin = userCard('Admin');
    expect(admin).toHaveTextContent("That's you.");
    expect(within(admin).queryByRole('button')).not.toBeInTheDocument();

    const ben = userCard('Ben');
    expect(ben).toHaveTextContent('@ben · joined 02/09/2026 · never seen');
    expect(within(ben).getByRole('button', { name: 'Make admin: Ben' })).toBeVisible();

    const carl = userCard('Carl');
    expect(carl).toHaveTextContent('Deactivated');
    expect(within(carl).getByRole('button', { name: 'Reactivate Carl' })).toBeVisible();
  });

  it('promotes a user', async () => {
    const { fetchMock, user } = renderAdmin('/me/admin/users', {
      'PATCH /api/admin/users/u-ben': { ...USERS[1], role: 'admin' },
    });

    await screen.findByTestId(testIds.adminUserList);
    await user.click(screen.getByRole('button', { name: 'Make admin: Ben' }));

    expect(
      await screen.findByRole('button', { name: 'Remove admin rights from Ben' }),
    ).toBeVisible();
    await expect(requestsTo(fetchMock, 'PATCH /api/admin/users/u-ben')[0]?.json()).resolves.toEqual(
      { role: 'admin' },
    );
  });

  it('deactivates after confirming and translates admin errors', async () => {
    const { user } = renderAdmin('/me/admin/users', {
      'PATCH /api/admin/users/u-ben': errorResponse(409, 'admin.last_admin'),
    });

    await screen.findByTestId(testIds.adminUserList);
    await user.click(screen.getByRole('button', { name: 'Deactivate Ben' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Deactivate Ben?' });
    await user.click(within(dialog).getByRole('button', { name: 'Deactivate' }));

    expect(await screen.findByText('At least one active admin must remain.')).toBeVisible();
  });

  it('deletes a user after a confirmation that names them', async () => {
    const { fetchMock, user } = renderAdmin('/me/admin/users', {
      'DELETE /api/admin/users/u-ben': null,
    });

    await screen.findByTestId(testIds.adminUserList);
    await user.click(screen.getByRole('button', { name: 'Delete Ben' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Delete Ben (@ben)?' });
    expect(dialog).toHaveTextContent("This can't be undone.");

    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(requestsTo(fetchMock, 'DELETE /api/admin/users/u-ben')).toHaveLength(0);

    await user.click(screen.getByRole('button', { name: 'Delete Ben' }));
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', {
        name: 'Delete for good',
      }),
    );

    await waitFor(() =>
      expect(within(screen.getByTestId(testIds.adminUserList)).queryByText('Ben')).toBeNull(),
    );
    expect(requestsTo(fetchMock, 'DELETE /api/admin/users/u-ben')).toHaveLength(1);
  });

  it('creates a reset link and shares it with a second tap', async () => {
    const share = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    const url = 'https://mealmate.example/reset#reset-code';
    const { user } = renderAdmin('/me/admin/users', {
      'POST /api/admin/users/u-ben/reset-link': { url, expires_at: '2026-09-27T10:00:00Z' },
    });

    await screen.findByTestId(testIds.adminUserList);
    await user.click(screen.getByRole('button', { name: 'Create a password reset link for Ben' }));

    const field = await screen.findByLabelText('Reset link for Ben');
    expect(field).toHaveValue(url);
    expect(share).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId(testIds.shareButton));

    expect(share).toHaveBeenCalledOnce();
    const [{ text }] = share.mock.calls[0] as unknown as [{ text: string }];
    expect(text).toMatch(/^Hi Ben, /);
    expect(text).toContain('1. Make sure Tailscale is on.');
    expect(text).toContain(`2. Tap this link and choose a new password: ${url}`);
  });
});

const INVITES: Invite[] = [
  {
    id: 'i1',
    status: 'open',
    created_at: '2026-09-26T10:00:00Z',
    expires_at: '2026-10-03T10:00:00Z',
    created_by: ADMIN_REF,
    used_by: null,
    tailscale_share_url: null,
  },
  {
    id: 'i2',
    status: 'used',
    created_at: '2026-09-20T10:00:00Z',
    expires_at: '2026-09-27T10:00:00Z',
    created_by: null,
    used_by: userRef('Ben', 'u-ben'),
    tailscale_share_url: null,
  },
  {
    id: 'i3',
    status: 'revoked',
    created_at: '2026-09-19T10:00:00Z',
    expires_at: '2026-09-26T10:00:00Z',
    created_by: ADMIN_REF,
    used_by: null,
    tailscale_share_url: null,
  },
];

describe('AdminInvitesScreen', () => {
  it('lists invites with their status and revokes an open one', async () => {
    const { fetchMock, user } = renderAdmin('/me/admin/invites', {
      'GET /api/admin/invites': INVITES,
      'DELETE /api/admin/invites/i1': null,
    });

    const list = await screen.findByTestId(testIds.inviteList);
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map((row) => within(row).getAllByText(/./)[0]?.textContent)).toEqual([
      'Open',
      'Used',
      'Revoked',
    ]);
    expect(rows[0]).toHaveTextContent('Valid until 03/10/2026');
    expect(rows[1]).toHaveTextContent('by Ben');
    expect(rows[1]).toHaveTextContent('by Deleted user');
    expect(within(list).getAllByRole('button')).toHaveLength(1);

    await user.click(within(list).getByRole('button', { name: /^Revoke the invite from/ }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'DELETE /api/admin/invites/i1')).toHaveLength(1),
    );
  });

  it('creates an invite with a Tailscale share link, then shares the two-step message', async () => {
    const share = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    const url = 'https://mealmate.example/join#invite-code';
    const tailscale = 'https://login.tailscale.com/admin/invite/abc';
    const { fetchMock, user } = renderAdmin('/me/admin/invites', {
      'GET /api/admin/invites': [],
      'POST /api/admin/invites': () =>
        Response.json(
          { invite: { ...INVITES[0], tailscale_share_url: tailscale }, url },
          { status: 201 },
        ),
    });

    expect(await screen.findByText('No invites yet.')).toBeVisible();
    await user.type(screen.getByLabelText('Tailscale share link (optional)'), tailscale);
    await user.click(screen.getByTestId(testIds.createInviteButton));

    expect(await screen.findByTestId(testIds.shareLinkUrl)).toHaveValue(url);
    await expect(requestsTo(fetchMock, 'POST /api/admin/invites')[0]?.json()).resolves.toEqual({
      tailscale_share_url: tailscale,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Share' }));
    const [{ text }] = share.mock.calls[0] as unknown as [{ text: string }];
    expect(text).toContain(`1. Accept the Tailscale share`);
    expect(text).toContain(tailscale);
    expect(text).toContain(`2. Then tap this link to create your account: ${url}`);
    expect(text.indexOf(tailscale)).toBeLessThan(text.indexOf(url));
  });

  it('shares in the admin’s language, without a Tailscale link if none was given', async () => {
    const share = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    const url = 'https://mealmate.example/join#invite-code';
    await i18n.changeLanguage('de');
    const { fetchMock, user } = renderAdmin('/me/admin/invites', {
      'GET /api/admin/invites': [],
      'POST /api/admin/invites': () => Response.json({ invite: INVITES[0], url }, { status: 201 }),
    });

    await user.click(await screen.findByRole('button', { name: 'Einladung erstellen' }));
    fireEvent.click(await screen.findByTestId(testIds.shareButton));

    await expect(requestsTo(fetchMock, 'POST /api/admin/invites')[0]?.json()).resolves.toEqual({
      tailscale_share_url: null,
    });
    const [{ text }] = share.mock.calls[0] as unknown as [{ text: string }];
    expect(text).toContain('1. Installier die Tailscale-App');
    expect(text).toContain(`2. Tipp dann auf diesen Link und leg dein Konto an: ${url}`);
  });

  it('explains a missing public URL', async () => {
    const { user } = renderAdmin('/me/admin/invites', {
      'GET /api/admin/invites': [],
      'POST /api/admin/invites': errorResponse(503, 'admin.public_url_missing'),
    });

    await user.click(await screen.findByTestId(testIds.createInviteButton));

    expect(await screen.findByRole('alert')).toHaveTextContent('MEALMATE_PUBLIC_URL');
    expect(screen.queryByTestId(testIds.shareLinkUrl)).not.toBeInTheDocument();
  });
});

describe('AdminEventsScreen', () => {
  it('describes each event with who and when', async () => {
    const ben = userRef('Ben', 'u-ben');
    const events: AdminEvent[] = [
      {
        id: 'e1',
        actor: ADMIN_REF,
        action: 'user.role_change',
        target: ben,
        details: { role: 'admin' },
        created_at: '2026-09-26T10:00:00Z',
      },
      {
        id: 'e2',
        actor: ADMIN_REF,
        action: 'user.deactivate',
        target: userRef('Carl', 'u-carl', true),
        details: {},
        created_at: '2026-09-25T10:00:00Z',
      },
      {
        id: 'e3',
        actor: null,
        action: 'invite.create',
        target: null,
        details: {},
        created_at: '2026-09-24T10:00:00Z',
      },
      {
        id: 'e4',
        actor: ADMIN_REF,
        action: 'user.reset_link',
        target: null,
        details: {},
        created_at: '2026-09-23T10:00:00Z',
      },
      {
        id: 'e5',
        actor: ADMIN_REF,
        // An action this app version doesn't know yet (e.g. from a newer backend).
        action: 'ingredient.merge' as AdminEvent['action'],
        target: null,
        details: {},
        created_at: '2026-09-22T10:00:00Z',
      },
    ];
    renderAdmin('/me/admin/events', { 'GET /api/admin/events': events });

    const list = await screen.findByTestId(testIds.eventList);
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map((row) => row.firstChild?.textContent)).toEqual([
      'Admin made Ben an admin',
      'Admin deactivated Carl (deactivated)',
      'Deleted user created an invite',
      'Admin created a password reset link for Deleted user',
      'Action by Admin',
    ]);
    expect(within(rows[0] as HTMLElement).getByText(/26\/09\/2026/)).toHaveAttribute(
      'datetime',
      '2026-09-26T10:00:00Z',
    );
  });
});
