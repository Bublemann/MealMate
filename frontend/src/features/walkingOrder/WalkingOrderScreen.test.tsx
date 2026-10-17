import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { errorResponse, goOffline, mockApi, requestsTo } from '@/test/api';
import { CATEGORIES_WITH_UNCATEGORIZED, CHEESE_COUNTER } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { savedOrder, walkingOrder } from '@/test/walkingOrder';
import { testIds } from '@/testIds';

type WalkingOrder = components['schemas']['WalkingOrder'];

const FOLLOWING = walkingOrder();
const IN_ORDER = ['Fruit & vegetables', 'Dairy & eggs', 'Cheese', 'Other', 'Uncategorized'];
/** Each row is 50 px high in `stubRowGeometry`. */
const ROW_HEIGHT = 50;

function renderPage(order: WalkingOrder = FOLLOWING, routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    'GET /api/walking-order': order,
    'PUT /api/walking-order': savedOrder(order),
    'DELETE /api/walking-order': null,
    ...routes,
  });
  return { fetchMock, ...renderApp('/me/walking-order') };
}

/** The rows, each as its text ("Cheese counter new"), in their order on the page. */
async function rows(): Promise<string[]> {
  const list = await screen.findByTestId(testIds.walkingOrderList);
  return within(list)
    .getAllByRole('listitem')
    .map((item) => item.textContent?.trim() ?? '');
}

async function sentOrders(fetchMock: ReturnType<typeof mockApi>) {
  return Promise.all(
    requestsTo(fetchMock, 'PUT /api/walking-order').map(
      (request) => request.clone().json() as Promise<unknown>,
    ),
  );
}

function followSwitch() {
  return screen.getByRole('switch', { name: "Use the admins' order" });
}

/** jsdom lays nothing out: each row of a list counts as 50 px high, one below the other. */
function stubRowGeometry() {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    if (this.tagName !== 'LI' || !this.parentElement) return new DOMRect();
    const index = [...this.parentElement.children].indexOf(this);
    return new DOMRect(0, index * ROW_HEIGHT, 320, ROW_HEIGHT);
  });
}

/** A finger dragging `handle` from one height on the screen to another (px from the top). */
function drag(handle: Element, from: number, to: number) {
  const pointer = { pointerId: 1, pointerType: 'touch', isPrimary: true, clientX: 10 };
  fireEvent.pointerDown(handle, { ...pointer, clientY: from });
  const steps = 4;
  for (let step = 1; step <= steps; step++) {
    fireEvent.pointerMove(handle, { ...pointer, clientY: from + ((to - from) * step) / steps });
  }
  fireEvent.pointerUp(handle, { ...pointer, clientY: to });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('WalkingOrderScreen (REF-01, D-48)', () => {
  it('lists the categories in the order, following the admins’ order by default', async () => {
    renderPage();

    expect(await screen.findByTestId(testIds.screenWalkingOrder)).toBeVisible();
    expect(await rows()).toEqual(IN_ORDER);
    expect(followSwitch()).toBeChecked();
    expect(screen.getByRole('button', { name: 'Move Fruit & vegetables up' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Fruit & vegetables down' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Move Uncategorized up' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Move Uncategorized down' })).toBeDisabled();
  });

  it('keeps the order as the own one once a category is moved; the switch goes off', async () => {
    const { fetchMock, user } = renderPage();

    await user.click(await screen.findByRole('button', { name: 'Move Cheese up' }));

    expect(await rows()).toEqual([
      'Fruit & vegetables',
      'Cheese',
      'Dairy & eggs',
      'Other',
      'Uncategorized',
    ]);
    expect(followSwitch()).not.toBeChecked();
    // The focus follows the moved category.
    expect(screen.getByRole('button', { name: 'Move Cheese up' })).toHaveFocus();
    await waitFor(async () =>
      expect(await sentOrders(fetchMock)).toEqual([
        {
          category_ids: [
            'cat-fruit_vegetables',
            'cat-cheese',
            'cat-dairy_eggs',
            'cat-other',
            'cat-uncategorized',
          ],
          moved_id: 'cat-cheese',
        },
      ]),
    );
    await waitFor(() => expect(followSwitch()).not.toBeChecked());
  });

  it('marks a category an admin added “new” until it is moved', async () => {
    const order = walkingOrder([...CATEGORIES_WITH_UNCATEGORIZED, CHEESE_COUNTER], {
      follows: false,
      fresh: [CHEESE_COUNTER.id],
    });
    const { fetchMock, user } = renderPage(order);
    expect(await rows()).toEqual([...IN_ORDER, 'Cheese counter new']);

    // Moving another category past it keeps the mark.
    await user.click(screen.getByRole('button', { name: 'Move Uncategorized down' }));
    await waitFor(() => expect(requestsTo(fetchMock, 'PUT /api/walking-order')).toHaveLength(1));
    await waitFor(async () =>
      expect(await rows()).toEqual([
        ...IN_ORDER.slice(0, -1),
        'Cheese counter new',
        'Uncategorized',
      ]),
    );

    await user.click(screen.getByRole('button', { name: 'Move Cheese counter up' }));
    await waitFor(async () =>
      expect(await rows()).toEqual([
        ...IN_ORDER.slice(0, -2),
        'Cheese counter',
        'Other',
        'Uncategorized',
      ]),
    );
  });

  it('drags a category by its handle, saving once when it is let go', async () => {
    stubRowGeometry();
    const { fetchMock } = renderPage();
    await rows();
    const handles = screen.getAllByTestId(testIds.walkingOrderHandle);

    // From the middle of the third row (Cheese) to the top of the first.
    drag(handles[2] as Element, 2.5 * ROW_HEIGHT, 10);

    expect(await rows()).toEqual([
      'Cheese',
      'Fruit & vegetables',
      'Dairy & eggs',
      'Other',
      'Uncategorized',
    ]);
    await waitFor(async () =>
      expect(await sentOrders(fetchMock)).toEqual([
        {
          category_ids: [
            'cat-cheese',
            'cat-fruit_vegetables',
            'cat-dairy_eggs',
            'cat-other',
            'cat-uncategorized',
          ],
          moved_id: 'cat-cheese',
        },
      ]),
    );
  });

  it('saves nothing when a drag ends where it started', async () => {
    stubRowGeometry();
    const { fetchMock } = renderPage();
    await rows();

    drag(screen.getAllByTestId(testIds.walkingOrderHandle)[1] as Element, 75, 80);

    expect(await rows()).toEqual(IN_ORDER);
    expect(requestsTo(fetchMock, 'PUT /api/walking-order')).toHaveLength(0);
  });

  it('turning the switch off keeps the admins’ order as the own one, without asking', async () => {
    const { fetchMock, user } = renderPage();
    await rows();

    await user.click(followSwitch());

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(async () =>
      expect(await sentOrders(fetchMock)).toEqual([
        {
          category_ids: [
            'cat-fruit_vegetables',
            'cat-dairy_eggs',
            'cat-cheese',
            'cat-other',
            'cat-uncategorized',
          ],
        },
      ]),
    );
    await waitFor(() => expect(followSwitch()).not.toBeChecked());
  });

  it('turning the switch back on asks first, then follows the admins’ order again', async () => {
    let current = walkingOrder([...CATEGORIES_WITH_UNCATEGORIZED].reverse(), { follows: false });
    const { fetchMock, user } = renderPage(current, {
      'GET /api/walking-order': () => current,
      'DELETE /api/walking-order': () => {
        current = FOLLOWING;
        return null;
      },
    });
    expect(await rows()).toEqual([...IN_ORDER].reverse());
    expect(followSwitch()).not.toBeChecked();

    await user.click(followSwitch());
    let dialog = await screen.findByRole('alertdialog', { name: "Use the admins' order?" });
    expect(dialog).toHaveTextContent('Your own order will be dropped.');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(requestsTo(fetchMock, 'DELETE /api/walking-order')).toHaveLength(0);
    expect(followSwitch()).not.toBeChecked();

    await user.click(followSwitch());
    dialog = await screen.findByRole('alertdialog', { name: "Use the admins' order?" });
    await user.click(within(dialog).getByRole('button', { name: 'Use it' }));

    await waitFor(() => expect(followSwitch()).toBeChecked());
    expect(requestsTo(fetchMock, 'DELETE /api/walking-order')).toHaveLength(1);
    await waitFor(async () => expect(await rows()).toEqual(IN_ORDER));
  });

  it('puts the order back and says why when saving fails', async () => {
    const { user } = renderPage(FOLLOWING, {
      'PUT /api/walking-order': errorResponse(500, 'common.internal'),
    });

    await user.click(await screen.findByRole('button', { name: 'Move Cheese up' }));

    expect(await screen.findByRole('alert')).toBeVisible();
    await waitFor(async () => expect(await rows()).toEqual(IN_ORDER));
    expect(followSwitch()).toBeChecked();
  });

  it('needs a connection to change the order (SYNC-09)', async () => {
    const { fetchMock } = renderPage();
    await rows();

    goOffline(fetchMock);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Move Cheese up' })).toBeDisabled(),
    );
    expect(followSwitch()).toBeDisabled();
  });
});
