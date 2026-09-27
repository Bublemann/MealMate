import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { errorResponse, mockApi, requestsTo, TEST_ADMIN } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

// jsdom has no canvas to decode camera frames: the scanner's decoder finds nothing here.
vi.mock('@/features/scanner/decoder', () => ({
  loadDecoder: vi.fn(() => Promise.resolve()),
  decodeVideoFrame: vi.fn(() => Promise.resolve(null)),
}));

const REQUEST_INFO = {
  client_host: '100.101.102.103',
  scheme: 'https',
  host_header: 'mealmate.example.ts.net',
  x_forwarded_for: '100.101.102.103',
  x_forwarded_proto: 'https',
};

function diagRoutes() {
  let cookie = false;
  return {
    'POST /api/auth/refresh': errorResponse(401, 'auth.session_expired'),
    'GET /api/health': { status: 'ok' },
    'GET /api/auth/diag/request': REQUEST_INFO,
    'POST /api/auth/diag/set': () => {
      cookie = true;
      return null;
    },
    'POST /api/auth/diag/check': () => ({ present: cookie }),
  };
}

/** The result line labelled `label` (its <dt>). */
function result(label: string): HTMLElement {
  const row = screen
    .getAllByTestId(testIds.diagResult)
    .find((element) => within(element).queryByText(label, { selector: 'dt' }));
  if (!row) throw new Error(`no result "${label}"`);
  return row;
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'share');
  Reflect.deleteProperty(navigator, 'mediaDevices');
  vi.restoreAllMocks();
});

describe('DiagnosticsScreen', () => {
  it('works signed out and collects the environment, the server view and the cookie test', async () => {
    const fetchMock = mockApi(diagRoutes());
    const { user } = renderApp('/diag', { user: null });

    expect(await screen.findByTestId(testIds.screenDiagnostics)).toBeVisible();
    expect(screen.getByRole('heading', { level: 1, name: 'Diagnostics' })).toBeVisible();
    expect(screen.queryByRole('navigation', { name: 'Main navigation' })).not.toBeInTheDocument();
    await waitFor(() => expect(result('Display mode')).toHaveTextContent('Info browser'));
    await waitFor(() => expect(result('App version')).toHaveTextContent('OK 2.0.0-alpha.1'));
    await waitFor(() =>
      expect(result('Request')).toHaveTextContent('OK client_host=100.101.102.103 scheme=https'),
    );
    expect(result('localStorage marker')).toHaveTextContent('Info no marker');

    await user.click(screen.getByRole('button', { name: 'Set cookie' }));
    await waitFor(() => expect(result('Cookie set')).toHaveTextContent('OK set in browser'));
    await user.click(screen.getByRole('button', { name: 'Check cookie' }));
    await waitFor(() => expect(result('Cookie check')).toHaveTextContent('OK present in browser'));
    // Through the app's client, like the refresh call whose cookie it stands in for.
    const [check] = requestsTo(fetchMock, 'POST /api/auth/diag/check');
    expect(check?.headers.get('X-MealMate-Client')).toBe('web');

    await user.click(screen.getByRole('button', { name: 'Write marker' }));
    expect(result('localStorage marker')).toHaveTextContent(/OK marker from \d{4}-/);

    const report = screen.getByTestId(testIds.diagReport);
    expect(report).toHaveTextContent('MealMate diagnostics report');
    expect(report).toHaveTextContent('iOS version (from Settings → General → About): ____');
    expect(report).toHaveTextContent('[ok] cookie.check: present in browser');
    expect(report).toHaveTextContent('[not run] share.now');
    // The report goes into a public repository: the tailnet is masked there, not on screen.
    expect(screen.getByText('Addresses are masked for the public repository.')).toBeVisible();
    expect(report).toHaveTextContent(
      '[ok] server.request: client_host=100.x.x.x scheme=https host=mealmate.<tailnet>.ts.net',
    );
    expect(report).not.toHaveTextContent('100.101.102.103');
    expect(result('Request')).toHaveTextContent('host=mealmate.example.ts.net');
  });

  it('sends no request before the start-up refresh has settled', async () => {
    let settle = () => {};
    const settled = new Promise<void>((resolve) => {
      settle = resolve;
    });
    const fetchMock = mockApi({
      ...diagRoutes(),
      'POST /api/auth/refresh': async () => {
        await settled;
        return errorResponse(401, 'auth.session_expired');
      },
    });
    renderApp('/diag', { user: null });

    expect(await screen.findByTestId(testIds.screenDiagnostics)).toBeVisible();
    // The device readings don't need the server.
    await waitFor(() => expect(result('Display mode')).toHaveTextContent('Info browser'));
    for (const name of [
      'Read again',
      'Share after 1 s',
      'Set cookie',
      'Check cookie',
      'Load again',
    ]) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
    expect(screen.getByRole('button', { name: 'Share now' })).toBeEnabled();
    expect(requestsTo(fetchMock, 'GET /api/version')).toHaveLength(0);
    expect(requestsTo(fetchMock, 'GET /api/auth/diag/request')).toHaveLength(0);

    settle();
    await waitFor(() => expect(result('App version')).toHaveTextContent('OK 2.0.0-alpha.1'));
    await waitFor(() => expect(result('Request')).toHaveTextContent('OK client_host='));
    expect(screen.getByRole('button', { name: 'Check cookie' })).toBeEnabled();
  });

  it('says how to switch the endpoints on when they answer 404', async () => {
    mockApi({ 'POST /api/auth/refresh': errorResponse(401, 'auth.session_expired') });
    const { user } = renderApp('/diag', { user: null });

    const hint = 'set MEALMATE_DIAGNOSTICS_ENABLED=true in /srv/mealmate/.env and restart';
    await waitFor(() => expect(result('Request')).toHaveTextContent(hint));
    await user.click(await screen.findByRole('button', { name: 'Check cookie' }));
    await waitFor(() => expect(result('Cookie check')).toHaveTextContent(hint));
    expect(screen.getByTestId(testIds.diagReport)).toHaveTextContent(
      '[failed] cookie.check: 404: diagnostics endpoints are off',
    );
  });

  it('shares within the tap, and again after a request and a wait', async () => {
    const fetchMock = mockApi(diagRoutes());
    const share = vi.fn(() => Promise.reject(new DOMException('', 'AbortError')));
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    const { user } = renderApp('/diag', { user: null });

    await user.click(await screen.findByRole('button', { name: 'Share now' }));
    await waitFor(() =>
      expect(result('Share now')).toHaveTextContent('OK AbortError: sheet opened'),
    );
    expect(share).toHaveBeenCalledWith({ text: 'MealMate share test' });

    await user.click(screen.getByRole('button', { name: 'Share after 1 s' }));
    // Not yet: first the request and the wait.
    expect(share).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Waiting 1 s…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Share now' })).toBeDisabled();
    await waitFor(() => expect(result('Share after 1 s')).toHaveTextContent(/after the tap\)$/), {
      timeout: 3000,
    });
    expect(share).toHaveBeenCalledTimes(2);
    const healthCall = fetchMock.mock.calls.findIndex(
      ([request]) => new URL(request.url).pathname === '/api/health',
    );
    expect(healthCall).toBeGreaterThanOrEqual(0);
    expect(fetchMock.mock.invocationCallOrder[healthCall]).toBeLessThan(
      share.mock.invocationCallOrder[1] ?? 0,
    );
    expect(screen.getByRole('button', { name: 'Share now' })).toBeEnabled();
  });

  it('notes a browser without a share sheet', async () => {
    mockApi(diagRoutes());
    const { user } = renderApp('/diag', { user: null });

    await user.click(await screen.findByRole('button', { name: 'Share now' }));
    await waitFor(() =>
      expect(result('Share now')).toHaveTextContent('Failed navigator.share is missing'),
    );
  });

  it('records the size of the camera frames next to the track settings (O-6)', async () => {
    mockApi(diagRoutes());
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
    const track = Object.assign(new EventTarget(), {
      stop: vi.fn(),
      getSettings: () => ({ width: 1920, height: 1080, facingMode: 'environment' }),
      getCapabilities: () => ({}),
    });
    const stream = { id: 'stream-1', getTracks: () => [track], getVideoTracks: () => [track] };
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: () => Promise.resolve(stream) },
      configurable: true,
    });
    const { user } = renderApp('/diag', { user: null });

    await user.click(await screen.findByRole('button', { name: 'Open scanner' }));
    await waitFor(() =>
      expect(result('Camera track')).toHaveTextContent('settings 1920×1080, frames ?'),
    );
    // Frames arrive turned (iOS 26): the preview's `resize` updates the result.
    const video = screen.getByTestId(testIds.scannerVideo);
    Object.defineProperty(video, 'videoWidth', { value: 1080, configurable: true });
    Object.defineProperty(video, 'videoHeight', { value: 1920, configurable: true });
    fireEvent(video, new Event('resize'));
    expect(result('Camera track')).toHaveTextContent(
      'settings 1920×1080, frames 1080×1920, facingMode environment',
    );
  });

  it('is linked from Me for admins, since a Home Screen app has no address bar', async () => {
    mockApi({ ...diagRoutes(), 'GET /api/me': TEST_ADMIN });
    const { user, router } = renderApp('/me', { user: TEST_ADMIN });

    await user.click(await screen.findByTestId(testIds.diagnosticsLink));
    expect(await screen.findByTestId(testIds.screenDiagnostics)).toBeVisible();
    expect(router.state.location.pathname).toBe('/diag');
  });

  it('is not linked from Me for other members of the household', async () => {
    mockApi(diagRoutes());
    renderApp('/me');

    expect(await screen.findByTestId(testIds.appVersion)).toBeVisible();
    expect(screen.queryByTestId(testIds.diagnosticsLink)).not.toBeInTheDocument();
  });
});
