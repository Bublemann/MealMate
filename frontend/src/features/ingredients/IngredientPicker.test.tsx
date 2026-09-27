import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { createQueryClient } from '@/app/queryClient';
import { mockApi, requestsTo } from '@/test/api';
import { ingredient, REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { testIds } from '@/testIds';
import type { IngredientSummary } from './api';
import { IngredientPicker } from './IngredientPicker';

const APPLES = summary('Äpfel', 'fruit_vegetables', { product_count: 2 });
const APPLE_JUICE = summary('Apfelsaft', 'other', { base_unit: 'ml' });

function renderPicker(
  props: Partial<Parameters<typeof IngredientPicker>[0]> = {},
  routes: Record<string, unknown> = {},
) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/ingredients': (request: Request) =>
      new URL(request.url).searchParams.get('q') === 'apf' ? [APPLES, APPLE_JUICE] : [],
    'GET /api/ingredients/similar': [],
    ...routes,
  });
  const onSelect = vi.fn<(ingredient: IngredientSummary) => void>();
  const queryClient = createQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <IngredientPicker onSelect={onSelect} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { fetchMock, onSelect, user: userEvent.setup() };
}

describe('IngredientPicker', () => {
  it('searches and picks an ingredient', async () => {
    const { fetchMock, onSelect, user } = renderPicker();

    expect(screen.getByText('Type a name to search.')).toBeVisible();
    await user.type(screen.getByLabelText('Search ingredient'), 'apf');

    const results = await screen.findByRole('list', { name: 'Matching ingredients' });
    const juice = await within(results).findByRole('button', { name: /^Apfelsaft/ });
    expect(juice).toHaveTextContent('Other · ml');
    await user.click(juice);

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLE_JUICE);
    // Only the finished word went to the server.
    expect(requestsTo(fetchMock, 'GET /api/ingredients')).toHaveLength(1);
  });

  it('leaves out excluded ingredients', async () => {
    const { user } = renderPicker({ excludeIds: [APPLES.id] });

    await user.type(screen.getByLabelText('Search ingredient'), 'apf');

    const results = await screen.findByRole('list', { name: 'Matching ingredients' });
    await within(results).findByRole('button', { name: /^Apfelsaft/ });
    expect(within(results).queryByRole('button', { name: /^Äpfel/ })).not.toBeInTheDocument();
  });

  it('moves through the results with the arrow keys', async () => {
    const { onSelect, user } = renderPicker();

    const input = screen.getByLabelText('Search ingredient');
    await user.type(input, 'apf');
    await screen.findByRole('button', { name: /^Apfelsaft/ });
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: /^Äpfel/ })).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(screen.getByTestId(testIds.ingredientPickerCreate)).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowUp}{ArrowUp}');
    expect(input).toHaveFocus();
    await user.keyboard('{ArrowDown}{Enter}');

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLES);
  });

  it('says when nothing matches and offers to create it', async () => {
    const { user } = renderPicker();

    await user.type(screen.getByLabelText('Search ingredient'), 'Quitten');

    expect(await screen.findByText('Nothing found.')).toBeVisible();
    expect(screen.getByTestId(testIds.ingredientPickerCreate)).toHaveTextContent(
      'Create “Quitten”',
    );
  });

  it('creates the typed ingredient inline and picks it', async () => {
    const created = ingredient({ id: 'ing-quitten', name: 'Quitten', category_id: 'cat-other' });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { 'POST /api/ingredients': Response.json(created, { status: 201 }) },
    );

    await user.type(screen.getByLabelText('Search ingredient'), 'Quitten');
    await user.click(await screen.findByTestId(testIds.ingredientPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Quitten');
    await user.click(within(dialog).getByRole('button', { name: 'Create ingredient' }));

    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledExactlyOnceWith({
        id: 'ing-quitten',
        name: 'Quitten',
        category_id: 'cat-other',
        base_unit: 'g',
        product_count: 0,
      }),
    );
    expect(dialog).not.toBeInTheDocument();
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toMatchObject({
      name: 'Quitten',
    });
  });

  it('picks a similar existing ingredient instead of creating a duplicate', async () => {
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { 'GET /api/ingredients/similar': [APPLES] },
    );

    await user.type(screen.getByLabelText('Search ingredient'), 'Apfl');
    await user.click(await screen.findByTestId(testIds.ingredientPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    const hint = await within(dialog).findByTestId(testIds.ingredientSimilar);
    await user.click(within(hint).getByRole('button', { name: 'Use Äpfel' }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLES);
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });
});
