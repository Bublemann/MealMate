import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { errorResponse, mockApi, requestsTo } from '@/test/api';
import { REFERENCE_ROUTES } from '@/test/ingredients';
import { recurringItem, recurringList, stubResizeObserver } from '@/test/recurring';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const KLOPAPIER = recurringItem();
const ITEM_PATH = `/api/recurring-items/${KLOPAPIER.id}`;

/** The page with Klopapier in the set; `PATCH` and `DELETE` answer as given. */
function renderPage(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/recurring-items': recurringList([KLOPAPIER]),
    [`PATCH ${ITEM_PATH}`]: KLOPAPIER,
    [`DELETE ${ITEM_PATH}`]: null,
    ...routes,
  });
  return { fetchMock, ...renderApp('/me/recurring') };
}

/** Taps Klopapier's row and returns its pop-up. */
async function openItem(user: ReturnType<typeof renderApp>['user']): Promise<HTMLElement> {
  const list = await screen.findByTestId(testIds.recurringList);
  await user.click(within(list).getByRole('button', { name: /^Klopapier/ }));
  return screen.findByRole('dialog', { name: 'Klopapier' });
}

function weeks(dialog: HTMLElement) {
  return within(dialog).getByRole('spinbutton', { name: 'Every weeks' });
}

function automatic(dialog: HTMLElement) {
  return within(dialog).getByRole('switch', { name: 'Adjust automatically' });
}

function lastBought(dialog: HTMLElement) {
  return within(dialog).getByLabelText('Last bought');
}

async function patchBodies(fetchMock: ReturnType<typeof mockApi>) {
  return Promise.all(requestsTo(fetchMock, `PATCH ${ITEM_PATH}`).map((request) => request.json()));
}

beforeEach(stubResizeObserver);

describe('the recurring pop-up, editing (LIST-16, D-42)', () => {
  it('opens from the row with the item’s values, “Save”, and “No longer recurring” last', async () => {
    const { user } = renderPage();

    const dialog = await openItem(user);

    expect(weeks(dialog)).toHaveValue(4);
    expect(automatic(dialog)).toBeChecked();
    expect(lastBought(dialog)).toHaveValue('2026-10-02');
    // The red "No longer recurring" comes last, after "Save" (the dialog's ✕ follows them).
    const [save, remove, close] = within(dialog).getAllByRole('button');
    expect(save).toHaveTextContent('Save');
    expect(remove).toHaveTextContent('No longer recurring');
    expect(remove).toBe(within(dialog).getByTestId(testIds.recurringRemove));
    expect(close).toHaveAccessibleName('Close');
  });

  it('turns “Adjust automatically” off when the interval changes and sends only that', async () => {
    const { fetchMock, user } = renderPage();
    const dialog = await openItem(user);

    await user.clear(weeks(dialog));
    await user.type(weeks(dialog), '2');
    expect(automatic(dialog)).not.toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await patchBodies(fetchMock)).toEqual([{ interval_weeks: 2, automatic: false }]);
    // The set loads again: the server sorts it and counts what is due.
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/recurring-items')).toHaveLength(2));
  });

  it('turns it on again when the interval is typed back, and then sends nothing', async () => {
    const { fetchMock, user } = renderPage();
    const dialog = await openItem(user);

    await user.clear(weeks(dialog));
    await user.type(weeks(dialog), '6');
    expect(automatic(dialog)).not.toBeChecked();
    await user.clear(weeks(dialog));
    await user.type(weeks(dialog), '4');
    expect(automatic(dialog)).toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, `PATCH ${ITEM_PATH}`)).toHaveLength(0);
  });

  it('leaves the switch as switched by hand when the interval is typed back', async () => {
    const { fetchMock, user } = renderPage();
    const dialog = await openItem(user);

    await user.click(automatic(dialog));
    await user.clear(weeks(dialog));
    await user.type(weeks(dialog), '6');
    await user.clear(weeks(dialog));
    await user.type(weeks(dialog), '4');
    expect(automatic(dialog)).not.toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await patchBodies(fetchMock)).toEqual([{ automatic: false }]);
  });

  it('can turn it back on after changing the interval', async () => {
    const { fetchMock, user } = renderPage();
    const dialog = await openItem(user);

    await user.clear(weeks(dialog));
    await user.type(weeks(dialog), '6');
    await user.click(automatic(dialog));
    expect(automatic(dialog)).toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await patchBodies(fetchMock)).toEqual([{ interval_weeks: 6, automatic: true }]);
  });

  it.each([
    [
      'the date',
      (dialog: HTMLElement) => {
        fireEvent.change(lastBought(dialog), { target: { value: '2026-09-28' } });
        return Promise.resolve();
      },
      { last_purchased_on: '2026-09-28' },
    ],
    [
      'only the switch',
      async (dialog: HTMLElement, user: ReturnType<typeof renderApp>['user']) => {
        await user.click(automatic(dialog));
      },
      { automatic: false },
    ],
  ])('sends %s alone when only it changed', async (_, change, body) => {
    const { fetchMock, user } = renderPage();
    const dialog = await openItem(user);

    await change(dialog, user);
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await patchBodies(fetchMock)).toEqual([body]);
  });

  it('shows the server’s field errors at their fields and stays open', async () => {
    const { user } = renderPage({
      [`PATCH ${ITEM_PATH}`]: errorResponse(422, 'common.validation', [
        { loc: ['body', 'interval_weeks'], code: 'out_of_range' },
        { loc: ['body', 'last_purchased_on'], code: 'out_of_range' },
      ]),
    });
    const dialog = await openItem(user);

    await user.clear(weeks(dialog));
    await user.type(weeks(dialog), '60');
    fireEvent.change(lastBought(dialog), { target: { value: '2030-01-01' } });
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(weeks(dialog)).toHaveAccessibleDescription('Out of range'));
    expect(weeks(dialog)).toBeInvalid();
    expect(lastBought(dialog)).toHaveAccessibleDescription('Out of range');
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();
  });

  it('removes the item with “No longer recurring” after asking', async () => {
    let items = [KLOPAPIER];
    const { fetchMock, user } = renderPage({
      'GET /api/recurring-items': () => recurringList(items),
      [`DELETE ${ITEM_PATH}`]: () => {
        items = [];
        return null;
      },
    });
    const dialog = await openItem(user);

    await user.click(within(dialog).getByTestId(testIds.recurringRemove));
    const confirm = await screen.findByRole('alertdialog', {
      name: 'Stop buying “Klopapier” regularly?',
    });
    expect(requestsTo(fetchMock, `DELETE ${ITEM_PATH}`)).toHaveLength(0);
    await user.click(within(confirm).getByRole('button', { name: 'No longer recurring' }));

    await waitFor(() => expect(requestsTo(fetchMock, `DELETE ${ITEM_PATH}`)).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(await screen.findByText(/toilet paper, toothpaste, shower gel, …/)).toBeVisible();
  });
});
