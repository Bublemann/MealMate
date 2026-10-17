import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  BEN,
  CARL,
  errorResponse,
  mockApi,
  NO_COUPLE,
  requestsTo,
  TEST_USER,
  userRef,
} from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

describe('CoupleScreen', () => {
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
    const { user } = renderApp('/me/couple');

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
    const { user } = renderApp('/me/couple');

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
    const { user } = renderApp('/me/couple');

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
    const { user } = renderApp('/me/couple');

    const section = await screen.findByTestId(testIds.coupleSection);
    const picker = await within(section).findByRole('combobox');
    await waitFor(() => expect(picker).toBeEnabled());
    await user.selectOptions(picker, 'Ben');
    await user.click(within(section).getByRole('button', { name: 'Send request' }));

    expect(await within(section).findByText('This person is already in a couple.')).toBeVisible();
  });
});
