import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { errorResponse, mockApi, requestsTo, TEST_USER } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

/** PATCH /api/me answers with the user updated by the request body. */
function patchMe(request: Request) {
  return request.json().then((body: object) => ({ ...TEST_USER, ...body }));
}

describe('PrivacyScreen', () => {
  it('toggles the privacy switches on the server (VIS-02)', async () => {
    const fetchMock = mockApi({ 'PATCH /api/me': patchMe });
    const { user } = renderApp('/me/privacy');

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
    const { user } = renderApp('/me/privacy');

    const meals = screen.getByRole('switch', { name: 'Meals public' });
    await user.click(meals);

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeVisible();
    expect(meals).toBeChecked();
  });
});
