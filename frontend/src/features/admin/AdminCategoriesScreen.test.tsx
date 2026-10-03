import { act, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { components } from '@/api/generated/schema';
import { errorResponse, mockApi, requestsTo, TEST_ADMIN } from '@/test/api';
import {
  CATEGORIES,
  CATEGORIES_AFTER_DELETE,
  CATEGORIES_WITH_UNCATEGORIZED,
  CHEESE_COUNTER,
  UNCATEGORIZED,
} from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

type Category = components['schemas']['Category'];

/** The server's answer to a new order: every category in it, numbered again. */
async function reordered(request: Request) {
  const { category_ids } = (await request.json()) as { category_ids: string[] };
  return category_ids.map((id, index) => ({
    ...[...CATEGORIES, CHEESE_COUNTER, UNCATEGORIZED].find((category) => category.id === id),
    sort_order: index,
  }));
}

/** A PUT of the order that waits for the test to answer it; `answers` holds one per request. */
function heldOrders() {
  const answers: (() => void)[] = [];
  const route = async (request: Request) => {
    const body = await reordered(request);
    await new Promise<void>((resolve) => answers.push(resolve));
    return body;
  };
  return { answers, route };
}

function renderCategories(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    'GET /api/me': TEST_ADMIN,
    'GET /api/categories': CATEGORIES,
    'PUT /api/admin/categories/order': reordered,
    ...routes,
  });
  return { fetchMock, ...renderApp('/me/admin/categories', { user: TEST_ADMIN }) };
}

function names(): string[] {
  const list = screen.getByTestId(testIds.adminCategoryList);
  return within(list)
    .getAllByRole('listitem')
    .map((item) => item.textContent ?? '');
}

async function sentOrders(fetchMock: ReturnType<typeof mockApi>) {
  return Promise.all(
    requestsTo(fetchMock, 'PUT /api/admin/categories/order').map(
      async (request) =>
        ((await request.clone().json()) as { category_ids: string[] }).category_ids,
    ),
  );
}

describe('AdminCategoriesScreen', () => {
  it('lists the categories in their order, reachable from the admin navigation', async () => {
    renderCategories();

    expect(await screen.findByTestId(testIds.screenAdminCategories)).toBeVisible();
    await screen.findByTestId(testIds.adminCategoryList);
    expect(names()).toEqual(['1Fruit & vegetables', '2Dairy & eggs', '3Cheese', '4Other']);
    const nav = screen.getByRole('navigation', { name: 'Administration' });
    expect(within(nav).getByRole('link', { name: 'Categories' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('button', { name: 'Move Fruit & vegetables up' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Other down' })).toBeDisabled();
    // Each name opens the category's dialog; there is no "Save order" any more.
    expect(screen.getByRole('button', { name: 'Cheese' })).toHaveAttribute(
      'aria-haspopup',
      'dialog',
    );
    expect(screen.queryByRole('button', { name: 'Save order' })).not.toBeInTheDocument();
    // The status line only speaks after a delete.
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('saves the order on every tap; the focus follows the moved category', async () => {
    const { fetchMock, user } = renderCategories();
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Move Cheese up' }));
    expect(names()).toEqual(['1Fruit & vegetables', '2Cheese', '3Dairy & eggs', '4Other']);
    expect(screen.getByRole('button', { name: 'Move Cheese up' })).toHaveFocus();
    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(1),
    );

    await user.click(screen.getByRole('button', { name: 'Move Cheese up' }));
    // At the top its "up" button is disabled, so the focus moves to "down".
    expect(screen.getByRole('button', { name: 'Move Cheese down' })).toHaveFocus();
    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(2),
    );
    await user.click(screen.getByRole('button', { name: 'Move Dairy & eggs down' }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(3),
    );
    expect(await sentOrders(fetchMock)).toEqual([
      ['cat-fruit_vegetables', 'cat-cheese', 'cat-dairy_eggs', 'cat-other'],
      ['cat-cheese', 'cat-fruit_vegetables', 'cat-dairy_eggs', 'cat-other'],
      ['cat-cheese', 'cat-fruit_vegetables', 'cat-other', 'cat-dairy_eggs'],
    ]);
    expect(names()).toEqual(['1Cheese', '2Fruit & vegetables', '3Other', '4Dairy & eggs']);
    expect(screen.getByRole('button', { name: 'Move Dairy & eggs up' })).toHaveFocus();
  });

  it('sends the taps one after another, each when the one before is answered', async () => {
    const { answers, route } = heldOrders();
    const { fetchMock, user } = renderCategories({ 'PUT /api/admin/categories/order': route });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Move Other up' }));
    await user.click(screen.getByRole('button', { name: 'Move Other up' }));
    await user.click(screen.getByRole('button', { name: 'Move Other up' }));
    expect(names()).toEqual(['1Other', '2Fruit & vegetables', '3Dairy & eggs', '4Cheese']);
    await waitFor(() => expect(answers).toHaveLength(1));
    expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(1);

    for (const sent of [2, 3]) {
      act(() => answers.shift()?.());
      await waitFor(() => expect(answers).toHaveLength(1));
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(sent);
      // The screen keeps the latest order while the earlier ones are answered.
      expect(names()).toEqual(['1Other', '2Fruit & vegetables', '3Dairy & eggs', '4Cheese']);
    }
    act(() => answers.shift()?.());

    expect(await sentOrders(fetchMock)).toEqual([
      ['cat-fruit_vegetables', 'cat-dairy_eggs', 'cat-other', 'cat-cheese'],
      ['cat-fruit_vegetables', 'cat-other', 'cat-dairy_eggs', 'cat-cheese'],
      ['cat-other', 'cat-fruit_vegetables', 'cat-dairy_eggs', 'cat-cheese'],
    ]);
    await waitFor(() =>
      expect(names()).toEqual(['1Other', '2Fruit & vegetables', '3Dairy & eggs', '4Cheese']),
    );
  });

  it('still saves a tap made just before leaving the screen (ADM-01)', async () => {
    const { answers, route } = heldOrders();
    const { fetchMock, user } = renderCategories({ 'PUT /api/admin/categories/order': route });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Move Other up' }));
    await user.click(screen.getByRole('button', { name: 'Move Other up' }));
    await user.click(screen.getByRole('link', { name: 'Back to Me' }));
    expect(await screen.findByTestId(testIds.screenMe)).toBeVisible();
    await waitFor(() => expect(answers).toHaveLength(1));

    act(() => answers.shift()?.());

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(2),
    );
    expect((await sentOrders(fetchMock))[1]).toEqual([
      'cat-fruit_vegetables',
      'cat-other',
      'cat-dairy_eggs',
      'cat-cheese',
    ]);
  });

  it('names a category still being added in an order tapped meanwhile (REF-01)', async () => {
    let answerAdd: (() => void) | undefined;
    const { fetchMock, user } = renderCategories({
      'POST /api/admin/categories': async () => {
        await new Promise<void>((resolve) => (answerAdd = resolve));
        return Response.json(CHEESE_COUNTER, { status: 201 });
      },
    });
    await screen.findByTestId(testIds.adminCategoryList);
    await user.click(screen.getByTestId(testIds.newCategory));
    const dialog = await screen.findByRole('dialog', { name: 'New category' });
    await user.type(within(dialog).getByLabelText('Name in German'), 'Käsetheke');
    await user.type(within(dialog).getByLabelText('Name in English'), 'Cheese counter');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(answerAdd).toBeDefined());

    // Closed before the new category is saved, then a move: it waits for the new category.
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Move Other up' }));
    expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(0);
    act(() => answerAdd?.());

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(1),
    );
    expect(await sentOrders(fetchMock)).toEqual([
      ['cat-fruit_vegetables', 'cat-dairy_eggs', 'cat-other', 'cat-cheese', 'cat-cheese-counter'],
    ]);
    await waitFor(() =>
      expect(names()).toEqual([
        '1Fruit & vegetables',
        '2Dairy & eggs',
        '3Other',
        '4Cheese',
        '5Cheese counter',
      ]),
    );
  });

  it('puts the order back and says why when saving fails', async () => {
    const { user } = renderCategories({
      'PUT /api/admin/categories/order': errorResponse(422, 'common.validation'),
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Move Other up' }));

    expect(await screen.findByText('Please check your input.')).toBeVisible();
    expect(names()).toEqual(['1Fruit & vegetables', '2Dairy & eggs', '3Cheese', '4Other']);
    // The focus stays with the category, back in its place.
    expect(screen.getByRole('button', { name: 'Move Other up' })).toHaveFocus();
  });

  it('adds a category at the end of the list (REF-01)', async () => {
    const { fetchMock, user } = renderCategories({
      'POST /api/admin/categories': Response.json(CHEESE_COUNTER, { status: 201 }),
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByTestId(testIds.newCategory));
    const dialog = await screen.findByRole('dialog', { name: 'New category' });
    expect(dialog).toHaveAttribute('data-testid', testIds.categoryDialog);
    const german = within(dialog).getByLabelText('Name in German');
    const english = within(dialog).getByLabelText('Name in English');
    expect(german).toHaveValue('');
    expect(english).toHaveValue('');
    const save = within(dialog).getByRole('button', { name: 'Save' });
    // Both names are required.
    expect(save).toBeDisabled();
    await user.type(german, ' Käsetheke ');
    expect(save).toBeDisabled();
    await user.type(english, 'Cheese counter');
    await user.click(save);

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await expect(requestsTo(fetchMock, 'POST /api/admin/categories')[0]?.json()).resolves.toEqual({
      names: { de: 'Käsetheke', en: 'Cheese counter' },
    });
    expect(names()).toEqual([
      '1Fruit & vegetables',
      '2Dairy & eggs',
      '3Cheese',
      '4Other',
      '5Cheese counter',
    ]);
    expect(screen.getByRole('button', { name: 'Move Cheese counter up' })).toBeEnabled();
    expect(screen.getByTestId(testIds.newCategory)).toHaveFocus();
  });

  it('renames a category from its name, in both languages (REF-01)', async () => {
    const cheese = CATEGORIES.find((category) => category.key === 'cheese') as Category;
    const renamed: Category = { ...cheese, names: { de: 'Käsetheke', en: 'Cheese counter' } };
    const { fetchMock, user } = renderCategories({
      'PATCH /api/admin/categories/cat-cheese': renamed,
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Cheese' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit category' });
    const german = within(dialog).getByLabelText('Name in German');
    const english = within(dialog).getByLabelText('Name in English');
    expect(german).toHaveValue('Käse');
    expect(english).toHaveValue('Cheese');
    await user.clear(german);
    await user.type(german, 'Käsetheke');
    await user.clear(english);
    await user.type(english, 'Cheese counter');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await expect(
      requestsTo(fetchMock, 'PATCH /api/admin/categories/cat-cheese')[0]?.json(),
    ).resolves.toEqual({ names: { de: 'Käsetheke', en: 'Cheese counter' } });
    expect(names()).toEqual(['1Fruit & vegetables', '2Dairy & eggs', '3Cheese counter', '4Other']);
    expect(screen.getByRole('button', { name: 'Cheese counter' })).toHaveFocus();
  });

  it('shows a taken name at its field and keeps the dialog open', async () => {
    const { user } = renderCategories({
      'POST /api/admin/categories': errorResponse(422, 'common.validation', [
        { loc: ['body', 'names', 'en'], code: 'taken' },
      ]),
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByTestId(testIds.newCategory));
    const dialog = await screen.findByRole('dialog', { name: 'New category' });
    await user.type(within(dialog).getByLabelText('Name in German'), 'Käsetheke');
    await user.type(within(dialog).getByLabelText('Name in English'), 'Cheese');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    const english = within(dialog).getByLabelText('Name in English');
    await waitFor(() => expect(english).toHaveAccessibleDescription('Already taken'));
    expect(english).toHaveAttribute('aria-invalid', 'true');
    expect(within(dialog).getByLabelText('Name in German')).not.toHaveAttribute('aria-invalid');
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();
    expect(dialog).toBeVisible();
  });

  it('shows other errors in the dialog', async () => {
    const { user } = renderCategories({
      'PATCH /api/admin/categories/cat-cheese': errorResponse(404, 'common.not_found'),
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Cheese' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit category' });
    await user.type(within(dialog).getByLabelText('Name in English'), ' counter');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(await within(dialog).findByRole('alert')).toBeVisible();
  });

  it('moves Uncategorized like any other category, but has no dialog for it (REF-01)', async () => {
    const { fetchMock, user } = renderCategories({
      'GET /api/categories': CATEGORIES_WITH_UNCATEGORIZED,
    });
    await screen.findByTestId(testIds.adminCategoryList);

    expect(names()).toEqual([
      '1Fruit & vegetables',
      '2Dairy & eggs',
      '3Cheese',
      '4Other',
      '5Uncategorized',
    ]);
    // Its name is plain text: it can't be renamed or deleted.
    expect(screen.queryByRole('button', { name: 'Uncategorized' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Move Uncategorized up' }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(1),
    );
    expect(await sentOrders(fetchMock)).toEqual([
      ['cat-fruit_vegetables', 'cat-dairy_eggs', 'cat-cheese', 'cat-uncategorized', 'cat-other'],
    ]);
  });

  it('leaves deleted categories out of the list and the order (D-30)', async () => {
    const { fetchMock, user } = renderCategories({
      'GET /api/categories': CATEGORIES_AFTER_DELETE,
    });
    await screen.findByTestId(testIds.adminCategoryList);

    expect(names()).toEqual(['1Fruit & vegetables', '2Dairy & eggs', '3Other', '4Uncategorized']);
    await user.click(screen.getByRole('button', { name: 'Move Uncategorized up' }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PUT /api/admin/categories/order')).toHaveLength(1),
    );
    expect(await sentOrders(fetchMock)).toEqual([
      ['cat-fruit_vegetables', 'cat-dairy_eggs', 'cat-uncategorized', 'cat-other'],
    ]);
  });

  it('offers "Delete" in the dialog of every category but Other (REF-01)', async () => {
    const { user } = renderCategories();
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Cheese' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit category' });
    expect(within(dialog).getByRole('button', { name: 'Delete' })).toBeEnabled();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'Other' }));
    const other = await screen.findByRole('dialog', { name: 'Edit category' });
    expect(within(other).getByRole('button', { name: 'Save' })).toBeVisible();
    expect(within(other).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });

  it('deletes a category once confirmed, naming what moves (REF-01)', async () => {
    let deleted = false;
    const { fetchMock, user } = renderCategories({
      'GET /api/categories': () =>
        deleted ? CATEGORIES_AFTER_DELETE : CATEGORIES_WITH_UNCATEGORIZED,
      'GET /api/admin/categories/cat-cheese/usage': { ingredients: 3, extra_items: 1 },
      'DELETE /api/admin/categories/cat-cheese': () => {
        deleted = true;
        return new Response(null, { status: 204 });
      },
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Cheese' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit category' });
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Cheese?' });
    await waitFor(() =>
      expect(confirm).toHaveAccessibleDescription(
        '3 ingredients move to “Uncategorized”. 1 free-text item on drafts moves to “Other”. ' +
          "Lists being shopped and done lists stay as they are. This can't be undone.",
      ),
    );
    expect(requestsTo(fetchMock, 'DELETE /api/admin/categories/cat-cheese')).toHaveLength(0);
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, 'DELETE /api/admin/categories/cat-cheese')).toHaveLength(1);
    expect(screen.getByRole('status')).toHaveTextContent('Category “Cheese” deleted.');
    // The categories load again, as the server now orders them.
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/categories')).toHaveLength(2));
    await waitFor(() =>
      expect(names()).toEqual(['1Fruit & vegetables', '2Dairy & eggs', '3Other', '4Uncategorized']),
    );
  });

  it('keeps the confirmation open and says why when deleting fails', async () => {
    const { user } = renderCategories({
      'GET /api/admin/categories/cat-cheese/usage': { ingredients: 0, extra_items: 0 },
      'DELETE /api/admin/categories/cat-cheese': errorResponse(409, 'category.not_deletable'),
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Cheese' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit category' });
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Cheese?' });
    await waitFor(() =>
      expect(within(confirm).getByRole('button', { name: 'Delete' })).toBeEnabled(),
    );
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    expect(await within(confirm).findByRole('alert')).toHaveTextContent(
      "This category always exists and can't be deleted.",
    );
    expect(confirm).toBeVisible();
  });
});
