import { focusManager, onlineManager } from '@tanstack/react-query';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { BEN, errorResponse, mockApi, requestsTo } from '@/test/api';
import {
  CANDLES_EXTRA_ID,
  checkedBy,
  doneList,
  FLOUR_EXTRA_ID,
  LIST_ID,
  LIST_ROUTES,
  listDetail,
  listMeal,
  shoppingList,
  SHOPPING_LINES,
} from '@/test/lists';
import { ME } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { POLL_INTERVAL_MS } from './api';

type Schemas = components['schemas'];

const BASE = `/api/lists/${LIST_ID}`;
const A_UUID_V7: unknown = expect.stringMatching(
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
);
const AN_ISO_TIME: unknown = expect.stringMatching(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/);

function renderList(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({ ...LIST_ROUTES, [`GET ${BASE}`]: shoppingList(), ...routes });
  return { fetchMock, ...renderApp(`/lists/${LIST_ID}`) };
}

async function bodyOf(fetchMock: ReturnType<typeof mockApi>, route: string, index = 0) {
  const request = requestsTo(fetchMock, route)[index];
  if (!request) throw new Error(`no request to ${route}`);
  return (await request.json()) as unknown;
}

function withLine(list: Schemas['ListDetail'], name: string, change: Partial<Schemas['ListLine']>) {
  return {
    ...list,
    lines: list.lines.map((line) => (line.name === name ? { ...line, ...change } : line)),
  };
}

function opsAnswer(list: Schemas['ListDetail'], status: 'applied' | 'rejected' = 'applied') {
  return {
    results: [
      { op_id: 'op', status, code: status === 'rejected' ? 'list.done' : null },
    ] satisfies Schemas['OpResult'][],
    list,
  };
}

/** The names of the lines still to buy, in order. */
function openLines() {
  return within(screen.getByTestId(testIds.shoppingLines))
    .getAllByTestId(testIds.shoppingLine)
    .map((line) => within(line).getByRole('checkbox').getAttribute('aria-label'));
}

function cartLines() {
  return within(screen.getByTestId(testIds.inTheCart))
    .queryAllByTestId(testIds.shoppingLine)
    .map((line) => within(line).getByRole('checkbox').getAttribute('aria-label'));
}

afterEach(() => {
  vi.useRealTimers();
  focusManager.setFocused(undefined);
  onlineManager.setOnline(true);
});

/** The ops sent so far, in order. */
async function sentOps(fetchMock: ReturnType<typeof mockApi>) {
  const requests = requestsTo(fetchMock, `POST ${BASE}/ops`);
  const bodies = await Promise.all(
    requests.map((request) => request.clone().json() as Promise<Schemas['OpsRequest']>),
  );
  return bodies.flatMap((body) => body.ops);
}

describe('start shopping (LIST-11)', () => {
  it('starts shopping from a draft and shows the shopping view', async () => {
    const { fetchMock, user } = renderList({
      [`GET ${BASE}`]: listDetail(),
      [`POST ${BASE}/start-shopping`]: shoppingList(),
    });

    await user.click(await screen.findByTestId(testIds.startShopping));

    expect(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' })).toBeVisible();
    expect(requestsTo(fetchMock, `POST ${BASE}/start-shopping`)).toHaveLength(1);
    expect(screen.queryByTestId(testIds.startShopping)).not.toBeInTheDocument();
    expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent('Saved');
  });

  it('is not offered on someone else’s draft', async () => {
    renderList({ [`GET ${BASE}`]: listDetail({ is_owner: false, can_edit: false }) });

    await screen.findByTestId(testIds.listLines);
    expect(screen.queryByTestId(testIds.startShopping)).not.toBeInTheDocument();
  });
});

describe('shopping view (SHOP-01)', () => {
  it('shows the lines to buy by category with big check boxes, the rest in the cart', async () => {
    renderList();

    const lines = await screen.findByTestId(testIds.shoppingLines);
    expect(
      within(lines)
        .getAllByRole('heading', { level: 3 })
        .map((heading) => heading.textContent),
    ).toEqual(['Fruit & vegetables', 'Other']);
    // Removed in the draft: not shown while shopping.
    expect(openLines()).toEqual([
      'Check off Zwiebeln',
      'Check off Geburtstagskerzen',
      'Check off Mehl',
    ]);
    expect(screen.queryByText('Eier')).not.toBeInTheDocument();

    const cart = screen.getByTestId(testIds.inTheCart);
    expect(within(cart).getByText('In the cart (2)')).toBeVisible();
    expect(cart).not.toHaveAttribute('open');
    expect(cartLines()).toEqual(['Uncheck Milch', 'Uncheck Salz']);
    const [milk, salt] = within(cart).getAllByTestId(testIds.shoppingLine) as [
      HTMLElement,
      HTMLElement,
    ];
    expect(within(milk).getByRole('checkbox')).toBeChecked();
    expect(within(milk).getByTestId(testIds.lineCheckedBy)).toHaveTextContent('B');
    expect(milk).toHaveTextContent('checked by Ben');
    expect(within(milk).getByText('Milch')).toHaveClass('line-through');
    expect(within(salt).getByTestId(testIds.lineCheckedBy)).toHaveTextContent('A');
    // The meals can still be changed, collapsed below (LIST-12).
    const meals = screen.getByTestId(testIds.shoppingMeals);
    expect(within(meals).getByText('Meals (3)')).toBeVisible();
    expect(meals).not.toHaveAttribute('open');
    expect(screen.getByTestId(testIds.listReminder)).toHaveTextContent('Toilet paper');
  });

  it('marks new lines and says what a checked line needs more of (LIST-12)', async () => {
    renderList();

    const lines = await screen.findByTestId(testIds.shoppingLines);
    const [candles, flour] = within(lines).getAllByTestId(testIds.shoppingLine).slice(1) as [
      HTMLElement,
      HTMLElement,
    ];
    expect(within(candles).getByTestId(testIds.lineNew)).toHaveTextContent('new');
    expect(within(candles).queryByTestId(testIds.lineNeedsMore)).not.toBeInTheDocument();
    const more = within(flour).getByTestId(testIds.lineNeedsMore);
    expect(more).toHaveTextContent('Needs more:+300 gnew unit+ some');
    expect(within(flour).queryByTestId(testIds.lineNew)).not.toBeInTheDocument();
  });

  it('shows "changed" for an edited free-text item, in German too', async () => {
    const { authSession } = renderList({
      [`GET ${BASE}`]: withLine(shoppingList(), 'Geburtstagskerzen', {
        new: false,
        needs_more: { grown: [], new_unit: false, new_unspecified: false, changed: true },
      }),
    });
    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');

    const box = await screen.findByRole('checkbox', { name: 'Geburtstagskerzen abhaken' });
    const row = box.closest('li')!;
    expect(within(row).getByTestId(testIds.lineNeedsMore)).toHaveTextContent('geändert');
    expect(screen.getByRole('checkbox', { name: 'Mehl abhaken' }).closest('li')).toHaveTextContent(
      '+300 g',
    );
    expect(screen.getByText('Im Wagen (2)')).toBeVisible();
  });

  it('checks a line off at once through the ops and applies the answer', async () => {
    let answer: (() => void) | undefined;
    const answered = withLine(shoppingList({ version: 6 }), 'Zwiebeln', checkedBy(ME));
    const { fetchMock, user } = renderList({
      [`POST ${BASE}/ops`]: () =>
        new Promise((resolve) => {
          answer = () => resolve(opsAnswer(answered));
        }),
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));

    // Optimistic: in the cart with my initial before the server answered.
    expect(cartLines()).toContain('Uncheck Zwiebeln');
    expect(openLines()).not.toContain('Check off Zwiebeln');
    expect(screen.getByText('In the cart (3)')).toBeInTheDocument();
    await waitFor(() => expect(answer).toBeDefined());
    await expect(bodyOf(fetchMock, `POST ${BASE}/ops`)).resolves.toEqual({
      ops: [
        {
          op_id: A_UUID_V7,
          at: AN_ISO_TIME,
          type: 'line.check',
          payload: { line_key: 'i:ing-zwiebeln', checked: true },
        },
      ],
    });
    act(() => answer?.());
    await waitFor(() => expect(cartLines()).toContain('Uncheck Zwiebeln'));
  });

  it('unchecks a line from the cart', async () => {
    const { fetchMock, user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(
        withLine(shoppingList({ version: 6 }), 'Milch', {
          checked: false,
          checked_by: null,
        }),
      ),
    });
    const cart = await screen.findByTestId(testIds.inTheCart);
    await user.click(within(cart).getByText('In the cart (2)'));

    await user.click(within(cart).getByRole('checkbox', { name: 'Uncheck Milch' }));

    expect(openLines()).toContain('Check off Milch');
    await expect(bodyOf(fetchMock, `POST ${BASE}/ops`)).resolves.toMatchObject({
      ops: [{ type: 'line.check', payload: { line_key: 'i:ing-milch', checked: false } }],
    });
  });

  it('moves a line back and says why when checking it off fails', async () => {
    const { user } = renderList({
      [`POST ${BASE}/ops`]: errorResponse(500, 'common.internal'),
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeVisible();
    await waitFor(() => expect(openLines()).toContain('Check off Zwiebeln'));
    expect(cartLines()).not.toContain('Uncheck Zwiebeln');
  });

  it('moves a line back when the network is gone, and the status line says so', async () => {
    const { user, fetchMock } = renderList();
    await screen.findByTestId(testIds.shoppingLines);
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));

    await user.click(screen.getByRole('checkbox', { name: 'Check off Zwiebeln' }));

    expect(await screen.findByText("Can't reach MealMate. Are you online?")).toBeVisible();
    expect(openLines()).toContain('Check off Zwiebeln');
    // The list is loaded again after the failure, which can't reach the server either.
    await waitFor(
      () =>
        expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent(
          "Can't reach MealMate – no signal or Tailscale off?",
        ),
      { timeout: 3000 },
    );
  });

  it('shows the list as it is when the server turned the check-off down', async () => {
    // Ben finished the list a moment ago.
    const { user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(doneList(), 'rejected'),
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));

    const lines = await screen.findByTestId(testIds.doneLines);
    expect(within(lines).getByText('Zwiebeln').closest('li')).toHaveTextContent('(not bought)');
  });

  it('adds a free-text item as an op while shopping (SHOP-02)', async () => {
    const { fetchMock, user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(shoppingList({ version: 6 })),
    });
    const input = await screen.findByTestId(testIds.extraItemInput);

    await user.type(input, 'Servietten{Enter}');

    await waitFor(() => expect(requestsTo(fetchMock, `POST ${BASE}/ops`)).toHaveLength(1));
    await expect(bodyOf(fetchMock, `POST ${BASE}/ops`)).resolves.toEqual({
      ops: [
        {
          op_id: A_UUID_V7,
          at: AN_ISO_TIME,
          type: 'extra.add',
          payload: { extra_id: A_UUID_V7, text: 'Servietten', category_key: 'other' },
        },
      ],
    });
    await waitFor(() => expect(input).toHaveValue(''));
    expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(0);
  });

  it('lets me change servings while shopping (LIST-12)', async () => {
    const { fetchMock, user } = renderList({
      [`PATCH ${BASE}/meals/lm-pancakes`]: shoppingList({ meals: [listMeal({ servings: 5 })] }),
    });
    const meals = await screen.findByTestId(testIds.shoppingMeals);

    await user.click(within(meals).getByText('Meals (3)'));
    await user.click(within(meals).getByRole('button', { name: 'More servings of Pfannkuchen' }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, `PATCH ${BASE}/meals/lm-pancakes`)).toHaveLength(1),
    );
    expect(within(meals).getByTestId(testIds.addMeals)).toBeVisible();
  });

  it('is read-only for someone who may not change the list', async () => {
    renderList({ [`GET ${BASE}`]: shoppingList({ is_owner: false, can_edit: false }) });

    expect(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' })).toBeDisabled();
    expect(screen.queryByTestId(testIds.finishShopping)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.extraItemInput)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.editShoppingItem)).not.toBeInTheDocument();
  });

  it('stamps each check-off when it is tapped, not when it is sent (SYNC-06)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const waiting: (() => void)[] = [];
    const { fetchMock } = renderList({
      [`POST ${BASE}/ops`]: () =>
        new Promise((resolve) => {
          waiting.push(() => resolve(opsAnswer(shoppingList({ version: 6 }))));
        }),
    });
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));
    await waitFor(() => expect(waiting).toHaveLength(1));
    const tapped = Date.now();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Check off Geburtstagskerzen' }));

    // The second tap waits for the answer to the first, which comes a minute later.
    vi.setSystemTime(tapped + 60_000);
    act(() => waiting[0]?.());
    await waitFor(() => expect(waiting).toHaveLength(2));
    act(() => waiting[1]?.());

    const [first, second] = await sentOps(fetchMock);
    expect(first?.op_id).not.toBe(second?.op_id);
    const at = Date.parse(second?.at ?? '');
    expect(at).toBeGreaterThanOrEqual(tapped);
    expect(at).toBeLessThan(tapped + 60_000);
    expect(Date.parse(first?.at ?? '')).toBeLessThanOrEqual(tapped);
  });
});

describe('focus and announcements while checking off', () => {
  it('moves the focus to the next line to buy and says the line is in the cart', async () => {
    const { user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(
        withLine(shoppingList({ version: 6 }), 'Zwiebeln', checkedBy(ME)),
      ),
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));

    await waitFor(() =>
      expect(screen.getByRole('checkbox', { name: 'Check off Geburtstagskerzen' })).toHaveFocus(),
    );
    expect(screen.getByTestId(testIds.shoppingAnnouncement)).toHaveTextContent(
      'Zwiebeln is in the cart',
    );
    expect(screen.getByTestId(testIds.shoppingAnnouncement)).toHaveAttribute('aria-live', 'polite');
  });

  it('keeps the focus on an unchecked line in its new place', async () => {
    const { user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(
        withLine(shoppingList({ version: 6 }), 'Milch', { checked: false, checked_by: null }),
      ),
    });
    const cart = await screen.findByTestId(testIds.inTheCart);
    await user.click(within(cart).getByText('In the cart (2)'));

    await user.click(within(cart).getByRole('checkbox', { name: 'Uncheck Milch' }));

    const box = await screen.findByRole('checkbox', { name: 'Check off Milch' });
    await waitFor(() => expect(box).toHaveFocus());
    expect(
      within(screen.getByTestId(testIds.shoppingLines)).getByRole('checkbox', {
        name: 'Check off Milch',
      }),
    ).toBe(box);
    expect(screen.getByTestId(testIds.shoppingAnnouncement)).toHaveTextContent(
      'Milch is back on the list',
    );
  });

  it('says it in German too', async () => {
    const { authSession, user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(shoppingList({ version: 6 })),
    });
    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');

    await user.click(await screen.findByRole('checkbox', { name: 'Mehl abhaken' }));

    expect(screen.getByTestId(testIds.shoppingAnnouncement)).toHaveTextContent('Mehl ist im Wagen');
    await changeLanguage('en');
  });
});

describe('extra items while shopping (LIST-12)', () => {
  async function openItem(user: ReturnType<typeof renderList>['user'], name: string) {
    await user.click(await screen.findByRole('button', { name: `Edit the item ${name}` }));
    return within(await screen.findByRole('dialog', { name: 'Edit item' }));
  }

  it('renames a free-text item through an op, trying again with the same op', async () => {
    let fail = true;
    const { fetchMock, user } = renderList({
      [`POST ${BASE}/ops`]: () =>
        fail ? errorResponse(500, 'common.internal') : opsAnswer(shoppingList({ version: 6 })),
    });
    const dialog = await openItem(user, 'Geburtstagskerzen');
    // A free-text item keeps its category while shopping.
    expect(dialog.queryByRole('combobox', { name: 'Category' })).not.toBeInTheDocument();

    const name = dialog.getByRole('textbox', { name: 'Name' });
    await user.clear(name);
    await user.type(name, 'Kerzen');
    await user.click(dialog.getByRole('button', { name: 'Save' }));
    expect(await dialog.findByText('Something went wrong. Please try again.')).toBeVisible();
    fail = false;
    await user.click(dialog.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const [first, again] = await sentOps(fetchMock);
    expect(first).toEqual({
      op_id: A_UUID_V7,
      at: AN_ISO_TIME,
      type: 'extra.update',
      payload: { extra_id: CANDLES_EXTRA_ID, text: 'Kerzen', amount_text: '2 Packungen' },
    });
    expect(again).toEqual(first);
    expect(requestsTo(fetchMock, `PATCH ${BASE}/extra-items/${CANDLES_EXTRA_ID}`)).toHaveLength(0);
  });

  it('removes a free-text item through an op', async () => {
    const { fetchMock, user } = renderList({
      [`POST ${BASE}/ops`]: opsAnswer(shoppingList({ version: 6 })),
    });
    const dialog = await openItem(user, 'Geburtstagskerzen');

    await user.click(dialog.getByRole('button', { name: 'Remove the item Geburtstagskerzen' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(await sentOps(fetchMock)).toEqual([
      {
        op_id: A_UUID_V7,
        at: AN_ISO_TIME,
        type: 'extra.delete',
        payload: { extra_id: CANDLES_EXTRA_ID },
      },
    ]);
  });

  it('changes the amount of a linked item and removes it through the item endpoints', async () => {
    const { fetchMock, user } = renderList({
      [`PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`]: shoppingList({ version: 6 }),
      [`DELETE ${BASE}/extra-items/${FLOUR_EXTRA_ID}`]: shoppingList({ version: 7 }),
    });
    let dialog = await openItem(user, 'Mehl');
    const amount = dialog.getByRole('textbox', { name: 'Amount (optional)' });
    await user.clear(amount);
    await user.type(amount, '500');
    await user.click(dialog.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await expect(bodyOf(fetchMock, `PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`)).resolves.toEqual(
      { amount: 500, unit: 'g' },
    );

    dialog = await openItem(user, 'Mehl');
    await user.click(dialog.getByRole('button', { name: 'Remove the item Mehl' }));
    await waitFor(() =>
      expect(requestsTo(fetchMock, `DELETE ${BASE}/extra-items/${FLOUR_EXTRA_ID}`)).toHaveLength(1),
    );
    expect(requestsTo(fetchMock, `POST ${BASE}/ops`)).toHaveLength(0);
  });

  it('has no edit button on lines without an extra item', async () => {
    renderList();

    const onions = (await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' })).closest(
      'li',
    )!;
    expect(within(onions).queryByTestId(testIds.editShoppingItem)).not.toBeInTheDocument();
    expect(screen.getAllByTestId(testIds.editShoppingItem)).toHaveLength(2);
  });

  it('sends a free-text item again with the same op after an error (SHOP-02)', async () => {
    let fail = true;
    const { fetchMock, user } = renderList({
      [`POST ${BASE}/ops`]: () =>
        fail ? errorResponse(500, 'common.internal') : opsAnswer(shoppingList({ version: 6 })),
    });
    const input = await screen.findByTestId(testIds.extraItemInput);
    await user.type(input, 'Servietten{Enter}');
    expect(await screen.findByText('Something went wrong. Please try again.')).toBeVisible();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Add Servietten' }));

    await waitFor(() => expect(input).toHaveValue(''));
    const [first, again] = await sentOps(fetchMock);
    expect(first).toMatchObject({ type: 'extra.add', op_id: A_UUID_V7 });
    expect(again).toEqual(first);
  });
});

describe('offline (until the outbox of M6)', () => {
  it('fails a check-off at once, moves the line back and says why', async () => {
    const { user, fetchMock } = renderList();
    await screen.findByTestId(testIds.shoppingLines);
    act(() => onlineManager.setOnline(false));
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));

    await user.click(screen.getByRole('checkbox', { name: 'Check off Zwiebeln' }));

    expect(await screen.findByText("Can't reach MealMate. Are you online?")).toBeVisible();
    expect(openLines()).toContain('Check off Zwiebeln');
    expect(requestsTo(fetchMock, `POST ${BASE}/ops`)).toHaveLength(1);
  });

  it('does not leave *Finish* waiting', async () => {
    const { user, fetchMock } = renderList();
    await user.click(await screen.findByTestId(testIds.finishShopping));
    const dialog = await screen.findByRole('dialog', { name: 'Finish shopping?' });
    act(() => onlineManager.setOnline(false));
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));

    await user.click(within(dialog).getByRole('button', { name: 'Finish' }));

    expect(await within(dialog).findByText("Can't reach MealMate. Are you online?")).toBeVisible();
    expect(within(dialog).getByRole('button', { name: 'Finish' })).toBeEnabled();
  });
});

describe('finish (SHOP-04)', () => {
  it('asks with the reminder and the unchecked count, and keeps shopping', async () => {
    const { user, fetchMock } = renderList();

    await user.click(await screen.findByTestId(testIds.finishShopping));

    const dialog = await screen.findByRole('dialog', { name: 'Finish shopping?' });
    expect(dialog).toHaveTextContent('3 items not checked');
    expect(dialog).toHaveTextContent("Reminder: Didn't forget anything? Toilet paper? Salt?");
    await user.click(within(dialog).getByRole('button', { name: 'Keep shopping' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, `POST ${BASE}/ops`)).toHaveLength(0);
  });

  it('finishes through the ops and shows the done list', async () => {
    const { user, fetchMock } = renderList({ [`POST ${BASE}/ops`]: opsAnswer(doneList()) });

    await user.click(await screen.findByTestId(testIds.finishShopping));
    const dialog = await screen.findByRole('dialog', { name: 'Finish shopping?' });
    await user.click(within(dialog).getByRole('button', { name: 'Finish' }));

    expect(await screen.findByTestId(testIds.doneLines)).toBeVisible();
    await expect(bodyOf(fetchMock, `POST ${BASE}/ops`)).resolves.toEqual({
      ops: [{ op_id: A_UUID_V7, at: AN_ISO_TIME, type: 'list.finish', payload: {} }],
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('sends *Finish* again as the same op after an error', async () => {
    let fail = true;
    const { user, fetchMock } = renderList({
      [`POST ${BASE}/ops`]: () =>
        fail ? errorResponse(500, 'common.internal') : opsAnswer(doneList()),
    });
    await user.click(await screen.findByTestId(testIds.finishShopping));
    const dialog = await screen.findByRole('dialog', { name: 'Finish shopping?' });

    await user.click(within(dialog).getByRole('button', { name: 'Finish' }));
    expect(
      await within(dialog).findByText('Something went wrong. Please try again.'),
    ).toBeVisible();
    fail = false;
    await user.click(within(dialog).getByRole('button', { name: 'Finish' }));

    expect(await screen.findByTestId(testIds.doneLines)).toBeVisible();
    const [first, again] = await sentOps(fetchMock);
    expect(first).toMatchObject({ type: 'list.finish', op_id: A_UUID_V7, at: AN_ISO_TIME });
    expect(again).toEqual(first);
  });

  it('offers to finish when the last line is checked off, once per visit', async () => {
    const lastOne = shoppingList({
      lines: SHOPPING_LINES.map((line) =>
        line.name === 'Zwiebeln' ? line : { ...line, ...checkedBy(BEN), needs_more: null },
      ),
    });
    const { user } = renderList({
      [`GET ${BASE}`]: lastOne,
      [`POST ${BASE}/ops`]: async (request: Request) => {
        const { ops } = (await request.json()) as Schemas['OpsRequest'];
        const op = ops[0]!;
        const checked = op.type === 'line.check' && op.payload.checked;
        return opsAnswer(
          withLine(lastOne, 'Zwiebeln', checked ? checkedBy(ME) : { checked: false }),
        );
      },
    });

    await user.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));

    const dialog = await screen.findByRole('dialog', { name: 'Finish shopping?' });
    expect(dialog).not.toHaveTextContent('not checked');
    await user.click(within(dialog).getByRole('button', { name: 'Keep shopping' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByText('Everything is in the cart.')).toBeVisible();
    // Nothing left to buy: the focus is on the cart.
    await waitFor(() => expect(screen.getByText('In the cart (5)')).toHaveFocus());

    // Unchecked and checked again: not offered a second time.
    await user.click(screen.getByText('In the cart (5)'));
    await user.click(screen.getByRole('checkbox', { name: 'Uncheck Zwiebeln' }));
    await user.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));
    await screen.findByRole('checkbox', { name: 'Uncheck Zwiebeln' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('polling (SYNC-08)', () => {
  const ETAG = 'W/"abc"';

  /** `GET` of the list with an ETag; `If-None-Match` with it answers 304 until `change` is set. */
  function etagRoute(state: { list: Schemas['ListDetail']; etag: string }) {
    return (request: Request) => {
      if (request.headers.get('If-None-Match') === state.etag) {
        return new Response(null, { status: 304, headers: { ETag: state.etag } });
      }
      return Response.json(state.list, { headers: { ETag: state.etag } });
    };
  }

  async function tick(ms = POLL_INTERVAL_MS) {
    await act(() => vi.advanceTimersByTimeAsync(ms));
  }

  it('checks every 5 seconds with the ETag, keeps the list on 304 and shows changes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const state = { list: shoppingList(), etag: ETAG };
    const { fetchMock } = renderList({ [`GET ${BASE}`]: etagRoute(state) });
    await screen.findByTestId(testIds.shoppingLines);
    const gets = () => requestsTo(fetchMock, `GET ${BASE}`);
    expect(gets()).toHaveLength(1);
    expect(gets()[0]!.headers.get('If-None-Match')).toBeNull();

    await tick();
    await waitFor(() => expect(gets()).toHaveLength(2));
    expect(gets()[1]!.headers.get('If-None-Match')).toBe(ETAG);
    expect(openLines()).toContain('Check off Zwiebeln');

    // Ben checks the onions off on his phone.
    state.list = withLine(shoppingList({ version: 6 }), 'Zwiebeln', checkedBy(BEN));
    state.etag = 'W/"def"';
    await tick();
    await waitFor(() => expect(cartLines()).toContain('Uncheck Zwiebeln'));
    expect(gets()[2]!.headers.get('If-None-Match')).toBe(ETAG);
    expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent('Saved');

    await tick();
    await waitFor(() => expect(gets()).toHaveLength(4));
    expect(gets()[3]!.headers.get('If-None-Match')).toBe('W/"def"');
  });

  it('pauses while the app is in the background and checks at once when it is back', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const state = { list: shoppingList(), etag: ETAG };
    const { fetchMock } = renderList({ [`GET ${BASE}`]: etagRoute(state) });
    await screen.findByTestId(testIds.shoppingLines);
    const gets = () => requestsTo(fetchMock, `GET ${BASE}`);

    act(() => focusManager.setFocused(false));
    await tick(3 * POLL_INTERVAL_MS);
    expect(gets()).toHaveLength(1);

    act(() => focusManager.setFocused(true));
    await waitFor(() => expect(gets()).toHaveLength(2));
  });

  it('ignores an answer older than the list on screen (version)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const state = { list: shoppingList(), etag: ETAG };
    const answered = withLine(shoppingList({ version: 7 }), 'Zwiebeln', checkedBy(ME));
    const { fetchMock, user } = renderList({
      [`GET ${BASE}`]: etagRoute(state),
      [`POST ${BASE}/ops`]: opsAnswer(answered),
    });
    await user.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));
    await waitFor(() => expect(requestsTo(fetchMock, `POST ${BASE}/ops`)).toHaveLength(1));

    // A replica that is behind still has version 5 without the check-off.
    state.etag = 'W/"old"';
    await tick();
    await waitFor(() => expect(requestsTo(fetchMock, `GET ${BASE}`)).toHaveLength(2));
    await tick(100);

    expect(cartLines()).toContain('Uncheck Zwiebeln');
  });

  it('ignores a load that answers while a check-off waits for its answer', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const state = { list: shoppingList(), etag: ETAG };
    let answer: (() => void) | undefined;
    const answered = withLine(shoppingList({ version: 6 }), 'Zwiebeln', checkedBy(ME));
    const { fetchMock } = renderList({
      [`GET ${BASE}`]: etagRoute(state),
      [`POST ${BASE}/ops`]: () =>
        new Promise((resolve) => {
          answer = () => resolve(opsAnswer(answered));
        }),
    });
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));
    await waitFor(() => expect(answer).toBeDefined());

    // The server hasn't applied it yet, so the poll answers the old list in full.
    state.etag = 'W/"other"';
    await tick();
    await waitFor(() => expect(requestsTo(fetchMock, `GET ${BASE}`)).toHaveLength(2));
    await tick(100);
    expect(cartLines()).toContain('Uncheck Zwiebeln');

    act(() => answer?.());
    await tick(100);
    expect(cartLines()).toContain('Uncheck Zwiebeln');
  });

  it('says when MealMate can’t be reached, and "Saved" again once it can', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let offline = false;
    const { fetchMock, user } = renderList({
      [`GET ${BASE}`]: () => {
        if (offline) throw new TypeError('Failed to fetch');
        return shoppingList();
      },
    });
    await screen.findByTestId(testIds.shoppingLines);
    const status = screen.getByTestId(testIds.syncStatus);
    expect(status).toHaveTextContent('Saved');

    offline = true;
    await tick();
    // One retry after a second, then the error.
    await tick(1_500);
    await waitFor(() =>
      expect(status).toHaveTextContent("Can't reach MealMate – no signal or Tailscale off?"),
    );
    // The list stays on screen, without an error box.
    expect(openLines()).toContain('Check off Zwiebeln');
    expect(screen.queryByText("Can't reach MealMate. Are you online?")).not.toBeInTheDocument();

    offline = false;
    const before = requestsTo(fetchMock, `GET ${BASE}`).length;
    await user.click(screen.getByTestId(testIds.refreshList));
    await waitFor(() =>
      expect(requestsTo(fetchMock, `GET ${BASE}`).length).toBeGreaterThan(before),
    );
    await waitFor(() => expect(status).toHaveTextContent('Saved'));
  });

  it('stops asking once the list is gone', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let gone = false;
    const { fetchMock } = renderList({
      [`GET ${BASE}`]: () => (gone ? errorResponse(404, 'common.not_found') : shoppingList()),
    });
    await screen.findByTestId(testIds.shoppingLines);

    gone = true;
    await tick();
    expect(await screen.findByText("This doesn't exist (any more).")).toBeVisible();
    const count = requestsTo(fetchMock, `GET ${BASE}`).length;
    await tick(3 * POLL_INTERVAL_MS);
    expect(requestsTo(fetchMock, `GET ${BASE}`)).toHaveLength(count);
  });
});

describe('done list (SHOP-05/06)', () => {
  it('shows bought lines and greys the others, read-only', async () => {
    renderList({ [`GET ${BASE}`]: doneList() });

    const lines = await screen.findByTestId(testIds.doneLines);
    expect(screen.getByTestId(testIds.listDone)).toHaveTextContent(
      "Bought on 26/09. Lines that weren't checked off are greyed out.",
    );
    const onions = within(lines).getByText('Zwiebeln').closest('li')!;
    const milk = within(lines).getByText('Milch').closest('li')!;
    expect(onions).toHaveTextContent('(not bought)');
    expect(onions).toHaveClass('text-muted-foreground');
    expect(milk).toHaveTextContent('(bought)');
    expect(milk).not.toHaveClass('text-muted-foreground');
    expect(within(lines).queryByText('Eier')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.renameList)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.extraItemInput)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /servings/ })).not.toBeInTheDocument();
    expect(screen.getByTestId(testIds.deleteList)).toBeVisible();
  });

  it('shops again: a new draft, saying how many meals were left out', async () => {
    const created = listDetail({ id: 'list-again', name: 'Wochenende' });
    const { user, router, fetchMock } = renderList({
      [`GET ${BASE}`]: doneList(),
      [`POST ${BASE}/shop-again`]: Response.json({ list: created, left_out: 1 }, { status: 201 }),
      'GET /api/lists/list-again': created,
    });

    await user.click(await screen.findByTestId(testIds.shopAgain));

    await waitFor(() => expect(router.state.location.pathname).toBe('/lists/list-again'));
    expect(await screen.findByTestId(testIds.listLeftOut)).toHaveTextContent(
      "1 meal was left out: you can't see it, or it no longer exists.",
    );
    expect(requestsTo(fetchMock, `POST ${BASE}/shop-again`)).toHaveLength(1);
  });

  it('reopens the list for shopping', async () => {
    const { user, fetchMock } = renderList({
      [`GET ${BASE}`]: doneList(),
      [`POST ${BASE}/reopen`]: shoppingList({ version: 10 }),
    });

    await user.click(await screen.findByTestId(testIds.reopenList));

    expect(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' })).toBeVisible();
    expect(requestsTo(fetchMock, `POST ${BASE}/reopen`)).toHaveLength(1);
  });

  it('offers only "Shop again" to someone who may not change the list', async () => {
    renderList({ [`GET ${BASE}`]: doneList({ is_owner: false, can_edit: false }) });

    expect(await screen.findByTestId(testIds.shopAgain)).toBeVisible();
    expect(screen.queryByTestId(testIds.reopenList)).not.toBeInTheDocument();
  });

  it('exports unchecked lines first and marks what was bought (EXP-02)', async () => {
    const share = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    renderList({ [`GET ${BASE}`]: doneList() });

    fireEvent.click(await screen.findByRole('button', { name: 'Share as text' }));

    const [[{ text }]] = share.mock.calls as unknown as [[{ text: string }]];
    expect(text).toContain(
      'Other\n- (not bought) Geburtstagskerzen: 2 Packungen\n- (not bought) Mehl: 850 g\n✓ Salz',
    );
    Reflect.deleteProperty(navigator, 'share');
  });
});
