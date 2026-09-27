import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { errorResponse, mockApi, requestsTo, TEST_ADMIN, VERSION_INFO } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import type { SystemInfo } from './api';

const NO_STATUS: SystemInfo = { ...VERSION_INFO, image_digest: null, backup: null, disk: null };

const WITH_STATUS: SystemInfo = {
  ...VERSION_INFO,
  image_digest: 'sha256:0123abcd',
  backup: {
    finished_at: '2026-09-27T12:15:04Z',
    label: 'pre-update',
    ok: true,
    size_bytes: 4_200_000,
    message: '<b>backup</b> 20260927T121500Z done',
  },
  disk: {
    checked_at: '2026-09-27T12:00:02Z',
    free_bytes: 18_600_000_000,
    total_bytes: 60_000_000_000,
    free_percent: 31,
  },
};

const ACCEPTED = () => new Response(null, { status: 202, headers: { 'Content-Length': '0' } });

function renderSystem(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    'GET /api/me': TEST_ADMIN,
    'GET /api/admin/system': NO_STATUS,
    'POST /api/admin/backup': ACCEPTED,
    ...routes,
  });
  return { fetchMock, ...renderApp('/me/admin/system', { user: TEST_ADMIN }) };
}

describe('AdminSystemScreen', () => {
  it('shows empty states while the server has not reported yet, reachable from the navigation', async () => {
    renderSystem();

    expect(await screen.findByTestId(testIds.screenAdminSystem)).toBeVisible();
    expect(await screen.findByTestId(testIds.systemVersion)).toHaveTextContent('2.0.0-alpha.1');
    const nav = screen.getByRole('navigation', { name: 'Administration' });
    expect(within(nav).getByRole('link', { name: 'System' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByText(VERSION_INFO.commit)).toBeVisible();
    expect(screen.queryByText('Image')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Source code/ })).toHaveAttribute(
      'href',
      VERSION_INFO.source_url,
    );
    expect(screen.getByTestId(testIds.backupStatus)).toHaveTextContent('No backup yet.');
    expect(screen.getByTestId(testIds.diskStatus)).toHaveTextContent('No disk check yet.');
  });

  it('shows the last backup and the free disk space', async () => {
    renderSystem({ 'GET /api/admin/system': WITH_STATUS });

    const backup = await screen.findByTestId(testIds.backupStatus);
    expect(within(backup).getByText('Successful')).toBeVisible();
    expect(within(backup).getByText(/27\/09\/2026/)).toHaveAttribute(
      'datetime',
      '2026-09-27T12:15:04Z',
    );
    expect(backup).toHaveTextContent('Before an update');
    expect(backup).toHaveTextContent('4.2 MB');
    // The host's message is plain text, never markup.
    expect(within(backup).getByText('<b>backup</b> 20260927T121500Z done')).toBeVisible();
    expect(screen.getByText('sha256:0123abcd')).toBeVisible();

    const disk = screen.getByTestId(testIds.diskStatus);
    expect(disk).toHaveTextContent('19 GB free of 60 GB (31%)');
    expect(disk).not.toHaveTextContent('running low');
    expect(disk).toHaveTextContent(/Checked 27\/09\/2026/);
  });

  it('marks a failed backup and low disk space', async () => {
    renderSystem({
      'GET /api/admin/system': {
        ...WITH_STATUS,
        backup: {
          ...WITH_STATUS.backup,
          ok: false,
          label: 'regular',
          size_bytes: null,
          message: null,
        },
        disk: { ...WITH_STATUS.disk, free_bytes: 6_000_000_000, free_percent: 10 },
      },
    });

    const backup = await screen.findByTestId(testIds.backupStatus);
    expect(within(backup).getByText('Failed')).toBeVisible();
    expect(backup).toHaveTextContent('Scheduled');
    expect(backup).not.toHaveTextContent('Size');
    expect(screen.getByTestId(testIds.diskStatus)).toHaveTextContent(
      'Space is running low: less than 20% is free.',
    );
  });

  it('requests a backup and says so', async () => {
    const { fetchMock, user } = renderSystem();

    await user.click(await screen.findByTestId(testIds.backupNow));

    expect(
      await screen.findByText(/^Backup requested\. The server starts it within a minute/),
    ).toBeVisible();
    expect(requestsTo(fetchMock, 'POST /api/admin/backup')).toHaveLength(1);
    // The status is loaded again.
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/admin/system')).toHaveLength(2));
  });

  it('explains the rate limit', async () => {
    const { user } = renderSystem({
      'POST /api/admin/backup': () => errorResponse(429, 'common.rate_limited'),
    });

    await user.click(await screen.findByTestId(testIds.backupNow));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      i18n.t('error.common.rate_limited', { lng: 'en' }),
    );
    expect(screen.queryByText(/^Backup requested/)).not.toBeInTheDocument();
  });

  it('shows a failed load', async () => {
    renderSystem({ 'GET /api/admin/system': errorResponse(503, 'common.service_unavailable') });

    expect(await screen.findByRole('alert')).toBeVisible();
    expect(screen.queryByTestId(testIds.backupNow)).not.toBeInTheDocument();
  });

  it('formats in German', async () => {
    await i18n.changeLanguage('de');
    renderSystem({ 'GET /api/admin/system': WITH_STATUS });

    const disk = await screen.findByTestId(testIds.diskStatus);
    expect(disk).toHaveTextContent('19 GB von 60 GB frei (31 %)');
    expect(screen.getByTestId(testIds.backupStatus)).toHaveTextContent('4,2 MB');
  });
});
