import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { goOffline, heldRoute, mockApi, requestsTo } from '@/test/api';
import type { components } from '@/api/generated/schema';
import {
  CHILI_SOURCE_ID,
  doneList,
  leftoverChili,
  LIST_ID,
  LIST_ROUTES,
  listDetail,
  listMeal,
  shoppingList,
} from '@/test/lists';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { UNDO_TOAST_MS } from './ListMeals';

const BASE = `/api/lists/${LIST_ID}`;

type Schemas = components['schemas'];

/** A leftover from the last done list (LIST-17). */
const CHILI = leftoverChili();
const PANCAKES = listMeal();

function opsAnswer(
  list: Schemas['ListDetail'],
  status: Schemas['OpResult']['status'] = 'applied',
  code: Schemas['OpResult']['code'] = null,
) {
  return { results: [{ op_id: 'op', status, code }], list };
}

/** The ops sent so far, in order, without their ids and times. */
async function sentOps(fetchMock: ReturnType<typeof mockApi>) {
  const bodies = await Promise.all(
    requestsTo(fetchMock, `POST ${BASE}/ops`).map(
      (request) => request.clone().json() as Promise<Schemas['OpsRequest']>,
    ),
  );
  return bodies.flatMap((body) => body.ops).map(({ type, payload }) => ({ type, payload }));
}

function eatenOp(eaten: boolean) {
  return { type: 'leftover.eaten', payload: { leftover_of: CHILI_SOURCE_ID, eaten } };
}

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

  it('takes a ticked leftover off the draft at once, queued as a change, and offers to undo it', async () => {
    const { user, fetchMock } = renderList({
      [`POST ${BASE}/ops`]: async (request: Request) => {
        const [op] = ((await request.json()) as Schemas['OpsRequest']).ops;
        return op?.payload && 'eaten' in op.payload && op.payload.eaten
          ? opsAnswer(listDetail({ version: 4, meals: [PANCAKES] }))
          : opsAnswer(listDetail({ version: 5, meals: [CHILI, PANCAKES] }));
      },
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Chili eaten' }));

    expect(screen.queryByRole('listitem', { name: 'Chili' })).not.toBeInTheDocument();
    const toast = await screen.findByTestId(testIds.leftoverToast);
    expect(toast).toHaveTextContent('Chili eaten');
    await waitFor(async () => expect(await sentOps(fetchMock)).toEqual([eatenOp(true)]));

    await user.click(within(toast).getByRole('button', { name: 'Undo' }));

    expect(await screen.findByRole('checkbox', { name: 'Chili eaten' })).not.toBeChecked();
    await waitFor(async () =>
      expect(await sentOps(fetchMock)).toEqual([eatenOp(true), eatenOp(false)]),
    );
    expect(screen.queryByTestId(testIds.leftoverToast)).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, `PUT ${BASE}/meals/lm-chili/eaten`)).toHaveLength(0);
  });

  it('ticks a leftover offline, and the undo too, and sends both once online (SYNC-03)', async () => {
    const { user, fetchMock } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(listDetail({ version: 5, meals: [CHILI, PANCAKES] })),
    });
    const box = await screen.findByRole('checkbox', { name: 'Chili eaten' });
    const answer = fetchMock.getMockImplementation();
    goOffline(fetchMock);
    await waitFor(() => expect(screen.getByTestId(testIds.offlineBanner)).toBeVisible());
    expect(box).toBeEnabled();
    expect(screen.getByTestId(testIds.offlineBanner)).toHaveTextContent(
      "You're offline. Ticking leftovers still works; everything else on this list needs a connection.",
    );

    await user.click(box);

    expect(screen.queryByRole('listitem', { name: 'Chili' })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent(
        'Offline – 1 change waiting',
      ),
    );
    await user.click(
      within(await screen.findByTestId(testIds.leftoverToast)).getByRole('button', {
        name: 'Undo',
      }),
    );
    expect(await screen.findByRole('checkbox', { name: 'Chili eaten' })).not.toBeChecked();
    expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent('Offline – 2 changes waiting');
    expect(requestsTo(fetchMock, `POST ${BASE}/ops`)).toHaveLength(0);

    // The connection is back.
    fetchMock.mockImplementation(answer!);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    await waitFor(async () =>
      expect(await sentOps(fetchMock)).toEqual([eatenOp(true), eatenOp(false)]),
    );
    await waitFor(() => expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent('Saved'));
  });

  it('closes the undo toast by itself, or when it is closed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(listDetail({ version: 4, meals: [PANCAKES] })),
    });
    await user.click(await screen.findByRole('checkbox', { name: 'Chili eaten' }));
    expect(await screen.findByTestId(testIds.leftoverToast)).toBeVisible();

    act(() => {
      vi.advanceTimersByTime(UNDO_TOAST_MS);
    });

    expect(screen.queryByTestId(testIds.leftoverToast)).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it('closes the undo toast with its close button', async () => {
    const { user, fetchMock } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(listDetail({ version: 4, meals: [PANCAKES] })),
    });
    await user.click(await screen.findByRole('checkbox', { name: 'Chili eaten' }));
    const toast = await screen.findByTestId(testIds.leftoverToast);

    await user.click(within(toast).getByRole('button', { name: 'Close' }));

    expect(screen.queryByTestId(testIds.leftoverToast)).not.toBeInTheDocument();
    await waitFor(() => expect(requestsTo(fetchMock, `POST ${BASE}/ops`)).toHaveLength(1));
  });

  it('shows the leftover again and says why when the server turns the tick down', async () => {
    // The couple ended: the done list is no longer mine to mark.
    const { user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(
        listDetail({ version: 4, meals: [CHILI, PANCAKES] }),
        'rejected',
        'common.forbidden',
      ),
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Chili eaten' }));

    expect(await screen.findByTestId(testIds.syncToast)).toHaveTextContent('could not be saved');
    expect(await screen.findByRole('checkbox', { name: 'Chili eaten' })).not.toBeChecked();
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

  it('needs a connection for its menu', async () => {
    const { fetchMock, user } = renderList();
    await screen.findByRole('checkbox', { name: 'Chili eaten' });

    goOffline(fetchMock);

    await waitFor(() => expect(screen.getByTestId(testIds.offlineBanner)).toBeVisible());
    // The ⋮ button stays enabled; its items need a connection (D-39).
    await user.click(screen.getByRole('button', { name: 'Actions: Chili' }));
    const menu = await screen.findByRole('menu');
    for (const id of [testIds.shopLeftover, testIds.removeLeftover])
      expect(within(menu).getByTestId(id)).toHaveAttribute('aria-disabled', 'true');
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
    const done = doneList({ meals: [{ ...CHILI, eaten: true }, PANCAKES] });
    const { user, fetchMock } = renderList({
      [`GET ${BASE}`]: done,
      [`PUT ${BASE}/meals/lm-chili/eaten`]: async (request: Request) =>
        doneList({
          version: 10,
          meals: [
            { ...CHILI, eaten: ((await request.json()) as { eaten: boolean }).eaten },
            PANCAKES,
          ],
        }),
    });

    const box = await screen.findByRole('checkbox', { name: 'Chili eaten' });
    expect(box).toBeChecked();
    expect(within(chiliRow()).getByText('left over')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Actions: Chili' })).not.toBeInTheDocument();
    // Unticked there, it stays on the done list, without a toast.
    await user.click(box);
    await waitFor(() =>
      expect(requestsTo(fetchMock, `PUT ${BASE}/meals/lm-chili/eaten`)).toHaveLength(1),
    );
    expect(chiliRow()).toBeVisible();
    await user.click(box);
    expect(chiliRow()).toBeVisible();
    expect(screen.queryByTestId(testIds.leftoverToast)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^Meals/ })).toHaveTextContent('Meals 1 of 2 eaten');
  });
});
