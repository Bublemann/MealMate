import { focusManager } from '@tanstack/react-query';
import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { BEN, errorResponse, mockApi, NO_COUPLE, requestsTo, TEST_USER, userRef } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const SECOND = 1000;

/** `n` incoming couple requests, from different people. */
function incoming(n: number) {
  return Array.from({ length: n }, (_, index) => ({
    id: `r${index}`,
    from_user: index === 0 ? BEN : userRef(`User ${index}`, `u${index}`),
    to_user: userRef('Anna', TEST_USER.id),
    created_at: '2026-09-26T10:00:00Z',
  }));
}

function gearTab() {
  return screen.getByTestId(testIds.tabMe);
}

/** The count drawn on the gear: hidden from screen readers, which hear it in the tab's name. */
function visibleCount() {
  return within(gearTab()).queryByText(/^\d+\+?$/);
}

function regainFocus() {
  act(() => {
    focusManager.setFocused(false);
    focusManager.setFocused(true);
  });
}

afterEach(() => {
  focusManager.setFocused(undefined);
  vi.useRealTimers();
});

describe('the count on the gear (UI-07, D-51)', () => {
  it('shows nothing without incoming couple requests', async () => {
    const fetchMock = mockApi();
    renderApp('/lists');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/couple')).toHaveLength(1));
    expect(gearTab()).toHaveAccessibleName('Settings');
    expect(visibleCount()).not.toBeInTheDocument();
  });

  it('counts an incoming request on every tab, in the tab name for screen readers', async () => {
    mockApi({ 'GET /api/couple': { ...NO_COUPLE, incoming: incoming(1) } });
    renderApp('/lists');

    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings, 1 new'));
    const count = visibleCount();
    expect(count).toHaveTextContent('1');
    expect(count?.closest('[aria-hidden="true"]')).not.toBeNull();
    expect(gearTab()).not.toHaveAttribute('aria-label');
  });

  it('names the count in German, with plural forms', async () => {
    const anna = { ...TEST_USER, language: 'de' as const };
    mockApi({ 'GET /api/me': anna, 'GET /api/couple': { ...NO_COUPLE, incoming: incoming(2) } });
    await i18n.changeLanguage('de');
    renderApp('/lists', { user: anna });

    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Einstellungen, 2 neu'));
  });

  it('reads "9+" above nine', async () => {
    mockApi({ 'GET /api/couple': { ...NO_COUPLE, incoming: incoming(10) } });
    renderApp('/lists');

    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings, 10 new'));
    expect(visibleCount()).toHaveTextContent('9+');
  });

  it.each([
    ['accepting', 'accept', 'Accept request from Ben', { ...NO_COUPLE, partner: BEN, since: null }],
    ['declining', 'decline', 'Decline request from Ben', NO_COUPLE],
  ])('is gone at once after %s the request on the Paar page', async (_, action, button, answer) => {
    mockApi({
      'GET /api/couple': { ...NO_COUPLE, incoming: incoming(1) },
      [`POST /api/couple/requests/r0/${action}`]: answer,
    });
    const { user } = renderApp('/me');

    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings, 1 new'));
    await user.click(screen.getByRole('link', { name: 'Couple 1 request' }));
    await user.click(await screen.findByRole('button', { name: button }));

    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings'));
    expect(visibleCount()).not.toBeInTheDocument();
  });

  it('shows a new request once the app is back in the foreground', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    let requests = incoming(0);
    const fetchMock = mockApi({ 'GET /api/couple': () => ({ ...NO_COUPLE, incoming: requests }) });
    renderApp('/lists');
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/couple')).toHaveLength(1));

    requests = incoming(1);
    // Within the usual 30 s, coming back asks nothing again…
    vi.setSystemTime(Date.now() + 20 * SECOND);
    regainFocus();
    expect(requestsTo(fetchMock, 'GET /api/couple')).toHaveLength(1);

    // …later it does.
    vi.setSystemTime(Date.now() + 20 * SECOND);
    regainFocus();
    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings, 1 new'));
  });

  it('checks every 60 s while the app is visible, never in the background', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let requests = incoming(0);
    const fetchMock = mockApi({ 'GET /api/couple': () => ({ ...NO_COUPLE, incoming: requests }) });
    renderApp('/lists');
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/couple')).toHaveLength(1));

    act(() => focusManager.setFocused(false));
    requests = incoming(1);
    await act(() => vi.advanceTimersByTimeAsync(3 * 60 * SECOND));
    expect(requestsTo(fetchMock, 'GET /api/couple')).toHaveLength(1);
    expect(gearTab()).toHaveAccessibleName('Settings');

    act(() => focusManager.setFocused(true));
    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings, 1 new'));
    const afterFocus = requestsTo(fetchMock, 'GET /api/couple').length;

    requests = incoming(2);
    await act(() => vi.advanceTimersByTimeAsync(60 * SECOND));
    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings, 2 new'));
    expect(requestsTo(fetchMock, 'GET /api/couple')).toHaveLength(afterFocus + 1);
  });

  it('keeps the last count, and shows no error in the tab bar, when a refresh fails', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    let failing = false;
    const fetchMock = mockApi({
      'GET /api/couple': () =>
        failing ? errorResponse(500, 'common.internal') : { ...NO_COUPLE, incoming: incoming(2) },
    });
    renderApp('/lists');
    await waitFor(() => expect(gearTab()).toHaveAccessibleName('Settings, 2 new'));

    failing = true;
    vi.setSystemTime(Date.now() + 31 * SECOND);
    regainFocus();
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/couple')).toHaveLength(2));

    expect(gearTab()).toHaveAccessibleName('Settings, 2 new');
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).queryByRole('alert')).not.toBeInTheDocument();
    expect(nav).not.toHaveTextContent('Something went wrong');
  });
});
