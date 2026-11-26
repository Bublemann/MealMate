import { screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { errorResponse, goOffline, heldRoute, mockApi, requestsTo } from '@/test/api';
import { doneList, LIST_ID, LIST_ROUTES, listDetail, listMeal, shoppingList } from '@/test/lists';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const BASE = `/api/lists/${LIST_ID}`;

/** A leftover from the last done list (LIST-17). */
const CHILI = listMeal({
  id: 'lm-chili',
  meal_id: 'meal-chili',
  name: 'Chili',
  thumb_url: null,
  servings: 2,
  leftover: true,
});
const PANCAKES = listMeal();

function renderList(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...LIST_ROUTES,
    [`GET ${BASE}`]: listDetail({ meals: [CHILI, PANCAKES] }),
    ...routes,
  });
  return { fetchMock, ...renderApp(`/lists/${LIST_ID}`) };
}

function chiliRow() {
  return screen.getByRole('listitem', { name: 'Chili' });
}

async function bodyOf(fetchMock: ReturnType<typeof mockApi>, route: string) {
  const [request] = requestsTo(fetchMock, route);
  if (!request) throw new Error(`no request to ${route}`);
  return (await request.json()) as unknown;
}

describe('leftover meals in a draft (LIST-17)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a leftover with its badge, hint and box, without a servings stepper', async () => {
    renderList();
    const box = await screen.findByRole('checkbox', { name: 'Chili eaten' });
    const row = chiliRow();

    expect(box).not.toBeChecked();
    expect(box).toBeEnabled();
    expect(within(row).getByText('left over')).toBeVisible();
    expect(within(row).getByText('Ingredients not on the list')).toBeVisible();
    expect(within(row).getByText('2 servings')).toBeVisible();
    expect(within(row).queryByRole('button', { name: /servings/ })).not.toBeInTheDocument();
    // A normal meal keeps its stepper and has no box.
    const pancakes = screen.getByRole('listitem', { name: 'Pfannkuchen' });
    expect(
      within(pancakes).getByRole('button', { name: 'More servings of Pfannkuchen' }),
    ).toBeVisible();
    expect(screen.queryByRole('checkbox', { name: 'Pfannkuchen eaten' })).not.toBeInTheDocument();
  });

  it('takes a ticked leftover off the draft at once and offers to undo it', async () => {
    const { user, fetchMock } = renderList({
      [`PUT ${BASE}/meals/lm-chili/eaten`]: async (request: Request) =>
        ((await request.json()) as { eaten: boolean }).eaten
          ? listDetail({ version: 4, meals: [PANCAKES] })
          : listDetail({ version: 5, meals: [CHILI, PANCAKES] }),
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Chili eaten' }));

    expect(screen.queryByRole('listitem', { name: 'Chili' })).not.toBeInTheDocument();
    const toast = await screen.findByTestId(testIds.leftoverToast);
    expect(toast).toHaveTextContent('Chili eaten');
    expect(await bodyOf(fetchMock, `PUT ${BASE}/meals/lm-chili/eaten`)).toEqual({ eaten: true });

    await user.click(within(toast).getByRole('button', { name: 'Undo' }));

    expect(await screen.findByRole('checkbox', { name: 'Chili eaten' })).not.toBeChecked();
    const requests = requestsTo(fetchMock, `PUT ${BASE}/meals/lm-chili/eaten`);
    expect(requests).toHaveLength(2);
    expect(await requests[1]?.json()).toEqual({ eaten: false });
    expect(screen.queryByTestId(testIds.leftoverToast)).not.toBeInTheDocument();
  });

  it('says when ticking fails and shows the leftover again', async () => {
    const { user } = renderList({
      [`PUT ${BASE}/meals/lm-chili/eaten`]: errorResponse(403, 'common.forbidden'),
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Chili eaten' }));

    expect(await screen.findByRole('alert')).toBeVisible();
    expect(await screen.findByRole('checkbox', { name: 'Chili eaten' })).not.toBeChecked();
    expect(screen.queryByTestId(testIds.leftoverToast)).not.toBeInTheDocument();
  });

  it('shops for a leftover after all from its menu', async () => {
    const held = heldRoute();
    const { user, fetchMock } = renderList({ [`POST ${BASE}/meals/lm-chili/shop`]: held.route });

    await user.click(await screen.findByRole('button', { name: 'Actions: Chili' }));
    const menu = await screen.findByRole('menu');
    expect(
      within(menu)
        .getAllByRole('menuitem')
        .map((item) => item.textContent),
    ).toEqual(['Shop for it after all', 'Remove']);
    await user.click(within(menu).getByRole('menuitem', { name: 'Shop for it after all' }));
    await held.answer(listDetail({ version: 4, meals: [{ ...CHILI, leftover: false }, PANCAKES] }));

    await waitFor(() =>
      expect(
        within(chiliRow()).getByRole('button', { name: 'More servings of Chili' }),
      ).toBeVisible(),
    );
    expect(within(chiliRow()).queryByText('left over')).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, `POST ${BASE}/meals/lm-chili/shop`)).toHaveLength(1);
  });

  it('removes a leftover from its menu', async () => {
    const { user, fetchMock } = renderList({
      [`DELETE ${BASE}/meals/lm-chili`]: listDetail({ version: 4, meals: [PANCAKES] }),
    });

    await user.click(await screen.findByRole('button', { name: 'Actions: Chili' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Remove' }));

    await waitFor(() =>
      expect(screen.queryByRole('listitem', { name: 'Chili' })).not.toBeInTheDocument(),
    );
    expect(requestsTo(fetchMock, `DELETE ${BASE}/meals/lm-chili`)).toHaveLength(1);
    expect(requestsTo(fetchMock, `PUT ${BASE}/meals/lm-chili/eaten`)).toHaveLength(0);
  });

  it('offers no shopping for a leftover whose meal is gone', async () => {
    const { user } = renderList({
      [`GET ${BASE}`]: listDetail({
        meals: [{ ...CHILI, meal_id: null, detached: 'deleted' }, PANCAKES],
      }),
    });

    await user.click(await screen.findByRole('button', { name: 'Actions: Chili' }));

    expect(await screen.findByRole('menuitem', { name: 'Shop for it after all' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('needs a connection', async () => {
    const { fetchMock } = renderList();
    const box = await screen.findByRole('checkbox', { name: 'Chili eaten' });

    goOffline(fetchMock);

    await waitFor(() => expect(box).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Actions: Chili' })).toBeDisabled();
  });

  it('keeps leftovers while shopping, with their box', async () => {
    const { user } = renderList({
      [`GET ${BASE}`]: shoppingList({ meals: [CHILI, PANCAKES] }),
    });
    await user.click(await screen.findByText(/^Meals \(2\)$/));

    expect(await screen.findByRole('checkbox', { name: 'Chili eaten' })).toBeEnabled();
    expect(within(chiliRow()).getByText('left over')).toBeVisible();
  });

  it('shows leftovers on a done list, ticked once eaten, without a menu', async () => {
    renderList({
      [`GET ${BASE}`]: doneList({ meals: [{ ...CHILI, eaten: true }, PANCAKES] }),
    });

    expect(await screen.findByRole('checkbox', { name: 'Chili eaten' })).toBeChecked();
    expect(within(chiliRow()).getByText('left over')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Actions: Chili' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^Meals/ })).toHaveTextContent('Meals 1 of 2 eaten');
  });
});
