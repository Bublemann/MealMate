import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { errorResponse, mockApi, requestsTo, TEST_ADMIN } from '@/test/api';
import { CATEGORIES } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

function renderCategories(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    'GET /api/me': TEST_ADMIN,
    'GET /api/categories': CATEGORIES,
    'PUT /api/admin/categories/order': async (request: Request) => {
      const { category_ids } = (await request.json()) as { category_ids: string[] };
      return category_ids.map((id, index) => ({
        ...CATEGORIES.find((category) => category.id === id),
        sort_order: index,
      }));
    },
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
    expect(screen.getByTestId(testIds.saveCategoryOrder)).toBeDisabled();
  });

  it('moves categories up and down and saves the new order', async () => {
    const { fetchMock, user } = renderCategories();
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Move Cheese up' }));
    expect(names()).toEqual(['1Fruit & vegetables', '2Cheese', '3Dairy & eggs', '4Other']);
    // The focus stays with the moved category.
    expect(screen.getByRole('button', { name: 'Move Cheese up' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Move Cheese up' }));
    // At the top its "up" button is disabled, so the focus moves to "down".
    expect(screen.getByRole('button', { name: 'Move Cheese down' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: 'Move Dairy & eggs down' }));
    expect(names()).toEqual(['1Cheese', '2Fruit & vegetables', '3Other', '4Dairy & eggs']);

    await user.click(screen.getByRole('button', { name: 'Save order' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Order saved.');
    await expect(
      requestsTo(fetchMock, 'PUT /api/admin/categories/order')[0]?.json(),
    ).resolves.toEqual({
      category_ids: ['cat-cheese', 'cat-fruit_vegetables', 'cat-other', 'cat-dairy_eggs'],
    });
    expect(screen.getByTestId(testIds.saveCategoryOrder)).toBeDisabled();
  });

  it('shows why saving failed', async () => {
    const { user } = renderCategories({
      'PUT /api/admin/categories/order': errorResponse(422, 'common.validation'),
    });
    await screen.findByTestId(testIds.adminCategoryList);

    await user.click(screen.getByRole('button', { name: 'Move Other up' }));
    await user.click(screen.getByRole('button', { name: 'Save order' }));

    await waitFor(() => expect(screen.getByText('Please check your input.')).toBeVisible());
    expect(screen.getByRole('status')).toHaveTextContent('');
  });
});
