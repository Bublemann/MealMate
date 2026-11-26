import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { errorResponse, mockApi, requestsTo, TEST_USER } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

/** PATCH /api/me answers with the user updated by the request body. */
function patchMe(request: Request) {
  return request.json().then((body: object) => ({ ...TEST_USER, ...body }));
}

describe('LeftoversScreen', () => {
  it('turns the carry-over of leftover meals off and on again on the server (LIST-17)', async () => {
    const fetchMock = mockApi({ 'PATCH /api/me': patchMe });
    const { user } = renderApp('/me/leftovers');

    expect(await screen.findByTestId(testIds.screenLeftovers)).toBeVisible();
    expect(screen.getByRole('heading', { level: 1, name: 'Leftover meals' })).toBeVisible();
    const carryOver = screen.getByRole('switch', { name: 'Carry over leftover meals' });
    expect(carryOver).toBe(screen.getByTestId(testIds.carryOverSwitch));
    expect(carryOver).toBeChecked();
    expect(carryOver).toHaveAccessibleDescription(
      "New lists bring along the meals of the last done list that haven't been eaten yet.",
    );

    await user.click(carryOver);

    await waitFor(() => expect(carryOver).not.toBeChecked());
    await waitFor(() => expect(carryOver).toBeEnabled());
    expect(carryOver).not.toBeChecked();
    const [off] = requestsTo(fetchMock, 'PATCH /api/me');
    await expect(off?.json()).resolves.toEqual({ carry_over_leftovers: false });

    await user.click(carryOver);
    await waitFor(() => expect(carryOver).toBeEnabled());
    expect(carryOver).toBeChecked();
    await expect(requestsTo(fetchMock, 'PATCH /api/me')[1]?.json()).resolves.toEqual({
      carry_over_leftovers: true,
    });
  });

  it('shows the setting saved on another device, loaded as the Settings tab opens', async () => {
    mockApi({ 'GET /api/me': { ...TEST_USER, carry_over_leftovers: false } });
    const { user } = renderApp('/me');

    const row = screen.getByRole('link', { name: /^Leftover meals/ });
    await waitFor(() => expect(row).toHaveAccessibleName('Leftover meals Off'));
    await user.click(row);

    const carryOver = await screen.findByRole('switch', { name: 'Carry over leftover meals' });
    expect(carryOver).not.toBeChecked();
  });

  it('shows a failed change and keeps the old state', async () => {
    mockApi({ 'PATCH /api/me': errorResponse(500, 'common.internal') });
    const { user } = renderApp('/me/leftovers');

    const carryOver = await screen.findByRole('switch', { name: 'Carry over leftover meals' });
    await user.click(carryOver);

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeVisible();
    expect(carryOver).toBeChecked();
  });
});
