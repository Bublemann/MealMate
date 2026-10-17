import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DEFAULT_ROUTES, errorResponse, mockApi, requestsTo, userRef } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

describe('SecurityScreen', () => {
  it('shows the password reset notice (ACC-10)', async () => {
    mockApi({
      'GET /api/me/security': {
        password_changed_at: '2026-09-20T10:00:00Z',
        password_reset_at: '2026-09-20T10:00:00Z',
        password_reset_by: userRef('Admin', 'a1'),
      },
    });
    renderApp('/me/security');

    expect(await screen.findByTestId(testIds.securityNotice)).toHaveTextContent(
      /^Your password was reset by Admin on 20\/09\/2026, \d\d:\d\d\.$/,
    );
  });

  it('changes the password and reports a wrong current password', async () => {
    let wrong = true;
    const fetchMock = mockApi({
      'POST /api/me/password': () => (wrong ? errorResponse(403, 'auth.password_incorrect') : null),
    });
    const { user } = renderApp('/me/security');

    await user.click(screen.getByTestId(testIds.changePasswordButton));
    const dialog = await screen.findByRole('dialog', { name: 'Change password' });
    expect(within(dialog).getByLabelText('Current password')).toHaveFocus();
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
    const { user } = renderApp('/me/security');

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

  it('logs out on all devices after confirming', async () => {
    const fetchMock = mockApi({ 'POST /api/auth/logout-all': null });
    const { user } = renderApp('/me/security');

    await user.click(screen.getByTestId(testIds.logoutAllButton));
    const dialog = await screen.findByRole('alertdialog', { name: 'Log out on all devices?' });
    await user.click(within(dialog).getByRole('button', { name: 'Log out everywhere' }));

    expect(await screen.findByTestId(testIds.screenLogin)).toBeVisible();
    const [request] = requestsTo(fetchMock, 'POST /api/auth/logout-all');
    expect(request?.headers.get('Authorization')).toBe('Bearer test-access-token');
  });
});
