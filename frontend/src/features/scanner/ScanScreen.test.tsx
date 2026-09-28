import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { errorResponse, mockApi, requestsTo } from '@/test/api';
import { APPLES, ingredient, REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { loadDecoder } from './decoder';

type Schemas = components['schemas'];

// jsdom has no camera, so the scanner shows its manual input: the path E2E and people without a
// camera take (BAR-01). The decoder itself is tested in decoder.test.ts.
vi.mock('./decoder', () => ({ loadDecoder: vi.fn(), decodeVideoFrame: vi.fn() }));

const BARCODE = '4006381333931';
const MILK = summary('Milch', 'dairy_eggs', { base_unit: 'ml' });
const BUTTER = summary('Butter', 'dairy_eggs');

const PROPOSAL: Schemas['ProductProposal'] = {
  name: 'Frische Vollmilch 3,5 %',
  brand: 'Weidehof',
  quantity_text: '1 l',
  pack_quantity: 1,
  pack_unit: 'l',
  nutrition_basis: 'ml',
  nutrients: { kcal: 64, protein: 3.4, carbs: 4.8, sugar: 4.8, fat: 3.5 },
  category_key: 'dairy_eggs',
  off_last_modified_at: '2026-09-01T10:00:00Z',
};

function lookup(overrides: Partial<Schemas['ProductLookup']> = {}): Schemas['ProductLookup'] {
  return {
    barcode: BARCODE,
    found_in: 'off',
    product: null,
    ingredient: null,
    proposal: PROPOSAL,
    suggestions: [MILK, BUTTER],
    off_unavailable: false,
    ...overrides,
  };
}

const NOT_FOUND = lookup({ found_in: 'none', proposal: null, suggestions: [] });

function savedProduct(request: Request) {
  return request.json().then((body: Schemas['ProductCreate']) => ({
    id: 'prod-new',
    ...body,
    created_by: null,
  }));
}

function renderScan(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/products/lookup': lookup(),
    'GET /api/ingredients/similar': [],
    'GET /api/ingredients': [MILK, BUTTER],
    'POST /api/products': savedProduct,
    'GET /api/ingredients/ing-milch': ingredient({ ...MILK, name: 'Milch' }),
    'GET /api/ingredients/ing-milch/products': [],
    ...routes,
  });
  return { fetchMock, ...renderApp('/scan') };
}

type User = ReturnType<typeof renderApp>['user'];

async function typeBarcode(user: User, barcode = BARCODE) {
  await user.type(await screen.findByRole('textbox', { name: 'Barcode' }), `${barcode}{Enter}`);
}

async function bodyOf(fetchMock: ReturnType<typeof mockApi>, route: string) {
  const request = requestsTo(fetchMock, route)[0];
  if (!request) throw new Error(`no request to ${route}`);
  return (await request.json()) as unknown;
}

beforeEach(() => {
  vi.mocked(loadDecoder).mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('ScanScreen', () => {
  it('shows the manual input when there is no camera', async () => {
    renderScan();

    expect(await screen.findByRole('heading', { level: 1, name: 'Scan barcode' })).toBeVisible();
    expect(screen.getByTestId(testIds.scannerCameraMessage)).toHaveTextContent(
      'No camera available',
    );
    expect(screen.getByRole('link', { name: 'All ingredients' })).toHaveAttribute(
      'href',
      '/ingredients',
    );
  });

  it('goes straight to the ingredient of a known barcode (BAR-02)', async () => {
    const { fetchMock, router, user } = renderScan({
      'GET /api/products/lookup': lookup({
        found_in: 'db',
        ingredient: summary('Äpfel', 'fruit_vegetables', { id: APPLES.id }),
        proposal: null,
        suggestions: [],
      }),
      'GET /api/ingredients/ing-aepfel': APPLES,
      'GET /api/ingredients/ing-aepfel/products': [],
    });

    await typeBarcode(user, '4006 3813 33931');

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-aepfel'));
    const [request] = requestsTo(fetchMock, 'GET /api/products/lookup');
    expect(new URL(request?.url ?? '').searchParams.get('barcode')).toBe(BARCODE);
  });

  it('shows the Open Food Facts proposal as text, with the attribution (BAR-03, BAR-09)', async () => {
    const { user } = renderScan({
      'GET /api/products/lookup': lookup({
        proposal: { ...PROPOSAL, name: '<b>Milch</b>' },
      }),
    });

    await typeBarcode(user);

    const card = await screen.findByTestId(testIds.scanProposal);
    expect(within(card).getByRole('heading', { name: '<b>Milch</b>' })).toBeVisible();
    expect(card).toHaveTextContent('Found at Open Food Facts');
    expect(card).toHaveTextContent('BrandWeidehof');
    expect(card).toHaveTextContent('Package size1 l');
    expect(card).toHaveTextContent(`Barcode${BARCODE}`);
    expect(card).toHaveTextContent('Nutrition per 100 ml');
    expect(card).toHaveTextContent('Calories64 kcal');
    expect(card).toHaveTextContent('Fat3.5 g');
    const link = within(card).getByRole('link', { name: /^Open Food Facts/ });
    expect(link).toHaveAttribute('href', 'https://world.openfoodfacts.org');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('heading', { name: 'Which ingredient is this?' })).toHaveFocus();
  });

  it('saves the proposal to a suggested ingredient, marking only corrected fields (BAR-04)', async () => {
    const { fetchMock, router, user } = renderScan();
    await typeBarcode(user);

    const suggestions = await screen.findByTestId(testIds.scanSuggestions);
    await user.click(within(suggestions).getByRole('button', { name: /^Milch/ }));

    expect(await screen.findByRole('heading', { name: 'Product for Milch' })).toHaveFocus();
    const form = screen.getByTestId(testIds.productForm);
    expect(within(form).getByLabelText('Barcode')).toHaveValue(BARCODE);
    expect(within(form).getByLabelText('Barcode')).toHaveAttribute('readonly');
    expect(within(form).getByLabelText('Product name')).toHaveValue('Frische Vollmilch 3,5 %');
    expect(within(form).getByLabelText('Unit of the contents')).toHaveValue('l');
    expect(within(form).getByRole('group', { name: 'Nutrition per 100 ml' })).toBeVisible();
    const kcal = within(form).getByLabelText('Calories');
    expect(kcal).toHaveValue('64');
    await user.clear(kcal);
    await user.type(kcal, '65');
    await user.click(within(form).getByRole('button', { name: 'Add product' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-milch'));
    expect(await bodyOf(fetchMock, 'POST /api/products')).toEqual({
      barcode: BARCODE,
      ingredient_id: 'ing-milch',
      source: 'off',
      off_last_modified_at: '2026-09-01T10:00:00Z',
      edited_fields: ['nutrients.kcal'],
      name: 'Frische Vollmilch 3,5 %',
      brand: 'Weidehof',
      quantity_text: '1 l',
      pack_quantity: 1,
      pack_unit: 'l',
      nutrition_basis: 'ml',
      nutrients: { kcal: 65, protein: 3.4, carbs: 4.8, sugar: 4.8, fat: 3.5 },
    });
  });

  it('never shows a negative zero from Open Food Facts as "-0"', async () => {
    // JSON can carry `-0`, and Intl.NumberFormat shows it with its sign.
    const zeros = lookup({
      proposal: { ...PROPOSAL, nutrients: { ...PROPOSAL.nutrients, fat: 0 } },
    });
    const text = JSON.stringify(zeros).replace('"fat":0', '"fat":-0');
    expect(text).toContain('"fat":-0');
    const { user } = renderScan({
      'GET /api/products/lookup': new Response(text, {
        headers: { 'Content-Type': 'application/json' },
      }),
    });
    await typeBarcode(user);

    const card = await screen.findByTestId(testIds.scanProposal);
    expect(card).toHaveTextContent('Fat0 g');
    expect(card).not.toHaveTextContent('-0');
    const suggestions = screen.getByTestId(testIds.scanSuggestions);
    await user.click(within(suggestions).getByRole('button', { name: /^Milch/ }));
    const form = await screen.findByTestId(testIds.productForm);
    expect(within(form).getByLabelText('Fat')).toHaveValue('0');
  });

  it('creates a new ingredient with the name, category and unit from the proposal', async () => {
    const created = ingredient({
      id: 'ing-vollmilch',
      name: 'Frische Vollmilch 3,5 %',
      category_id: 'cat-dairy_eggs',
      base_unit: 'ml',
    });
    const { fetchMock, router, user } = renderScan({
      'POST /api/ingredients': created,
      'GET /api/ingredients/ing-vollmilch': created,
      'GET /api/ingredients/ing-vollmilch/products': [],
    });
    await typeBarcode(user);

    await user.click(await screen.findByTestId(testIds.scanCreateIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Frische Vollmilch 3,5 %');
    await waitFor(() =>
      expect(within(dialog).getByLabelText('Category')).toHaveValue('cat-dairy_eggs'),
    );
    expect(within(dialog).getByRole('radio', { name: 'Millilitres (ml)' })).toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: 'Create ingredient' }));

    expect(
      await screen.findByRole('heading', { name: 'Product for Frische Vollmilch 3,5 %' }),
    ).toBeVisible();
    expect(await bodyOf(fetchMock, 'POST /api/ingredients')).toEqual({
      name: 'Frische Vollmilch 3,5 %',
      base_unit: 'ml',
      category_id: 'cat-dairy_eggs',
    });
    await user.click(screen.getByRole('button', { name: 'Add product' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-vollmilch'));
    expect(await bodyOf(fetchMock, 'POST /api/products')).toMatchObject({
      ingredient_id: 'ing-vollmilch',
      source: 'off',
      edited_fields: [],
    });
  });

  it('asks for the values of a barcode Open Food Facts does not know', async () => {
    const { fetchMock, router, user } = renderScan({ 'GET /api/products/lookup': NOT_FOUND });
    await typeBarcode(user);

    // The barcode looked up shows, so that a misread code can be seen.
    expect(await screen.findByTestId(testIds.scanNotice)).toHaveTextContent(
      `Not found (${BARCODE}) – enter the values yourself.`,
    );
    expect(screen.queryByTestId(testIds.scanProposal)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.scanSuggestions)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.offAttribution)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Search another ingredient'), 'Mil');
    await user.click(await screen.findByRole('button', { name: /^Milch/ }));

    const form = await screen.findByTestId(testIds.productForm);
    expect(screen.getByText('Enter the values from the package.')).toBeVisible();
    expect(within(form).getByLabelText('Barcode')).toHaveValue(BARCODE);
    expect(within(form).getByLabelText('Barcode')).not.toHaveAttribute('readonly');
    expect(within(form).getByLabelText('Product name')).toHaveValue('');
    await user.type(within(form).getByLabelText('Calories'), '64');
    await user.click(within(form).getByRole('button', { name: 'Add product' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-milch'));
    expect(await bodyOf(fetchMock, 'POST /api/products')).toEqual({
      barcode: BARCODE,
      ingredient_id: 'ing-milch',
      source: 'manual',
      nutrients: { kcal: 64 },
    });
  });

  it('says when Open Food Facts could not be asked and tries again on request', async () => {
    let answers = 0;
    const { user } = renderScan({
      'GET /api/products/lookup': () => {
        answers += 1;
        return answers === 1 ? { ...NOT_FOUND, off_unavailable: true } : lookup();
      },
    });
    await typeBarcode(user);

    expect(await screen.findByTestId(testIds.scanNotice)).toHaveTextContent(
      `Open Food Facts is slow (${BARCODE}) – try again or enter the values yourself.`,
    );
    // The values can be entered right away …
    expect(screen.getByTestId(testIds.scanWhich)).toBeVisible();
    // … or Open Food Facts asked again.
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByTestId(testIds.scanProposal)).toBeVisible();
  });

  it('offers to try again or enter the values when Open Food Facts is busy', async () => {
    const { user } = renderScan({
      'GET /api/products/lookup': errorResponse(503, 'off.busy'),
    });
    await typeBarcode(user);

    expect(await screen.findByTestId(testIds.scanNotice)).toHaveTextContent(
      `Open Food Facts is slow (${BARCODE})`,
    );
    expect(screen.getByTestId(testIds.scanAgain)).toHaveTextContent('Scan again');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeVisible();
    await user.click(screen.getByTestId(testIds.scanEnterManually));

    expect(await screen.findByRole('heading', { name: 'Which ingredient is this?' })).toBeVisible();
    await user.click(screen.getByTestId(testIds.scanCreateIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('');
  });

  it('gives a lookup 25 s before it counts as slow (plan § 8)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockApi({ ...REFERENCE_ROUTES });
    // A lookup that never answers, until the client gives up.
    vi.stubGlobal('fetch', (request: Request, init?: RequestInit) => {
      if (new URL(request.url).pathname !== '/api/products/lookup') return fetchMock(request);
      return new Promise((_, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('', 'AbortError')));
      });
    });
    const { user } = renderApp('/scan');
    await typeBarcode(user);
    expect(await screen.findByText(`Looking up ${BARCODE}…`)).toBeVisible();

    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(screen.getByText(`Looking up ${BARCODE}…`)).toBeVisible();
    await act(() => vi.advanceTimersByTimeAsync(15_000));
    expect(await screen.findByTestId(testIds.scanNotice)).toHaveTextContent(
      'Open Food Facts is slow',
    );
  });

  it('says so when the barcode has a wrong check digit and lets it be typed again', async () => {
    const { user } = renderScan({
      'GET /api/products/lookup': errorResponse(422, 'common.validation', [
        { loc: ['query', 'barcode'], code: 'invalid_format' },
      ]),
    });
    await typeBarcode(user, '4006381333932');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "4006381333932 isn't a valid barcode. Please check the digits.",
    );
    expect(screen.getByRole('textbox', { name: 'Barcode' })).toBeVisible();
  });

  it('explains a nutrition basis that does not fit the ingredient', async () => {
    const { user } = renderScan({
      'POST /api/products': errorResponse(409, 'product.basis_mismatch'),
    });
    await typeBarcode(user);
    const suggestions = await screen.findByTestId(testIds.scanSuggestions);
    await user.click(within(suggestions).getByRole('button', { name: /^Butter/ }));
    await user.click(await screen.findByRole('button', { name: 'Add product' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "The product's values must refer to the ingredient's base unit.",
    );
    expect(
      screen.getByText(
        "This product's values are per 100 ml, the ingredient's per 100 g. Choose or create an ingredient measured in ml.",
      ),
    ).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Choose another ingredient' }));
    expect(await screen.findByTestId(testIds.scanWhich)).toBeVisible();
  });

  it.each([
    ['not found', NOT_FOUND],
    ['Open Food Facts slow', { ...NOT_FOUND, off_unavailable: true }],
  ])('scans again straight from the notice (%s)', async (_case, answer) => {
    const { fetchMock, user } = renderScan({ 'GET /api/products/lookup': answer });
    await typeBarcode(user);
    await screen.findByTestId(testIds.scanNotice);

    await user.click(screen.getByRole('button', { name: 'Scan again' }));

    expect(await screen.findByRole('textbox', { name: 'Barcode' })).toHaveValue('');
    expect(screen.queryByTestId(testIds.scanNotice)).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, 'GET /api/products/lookup')).toHaveLength(1);
  });

  it('scans again from the notice of a barcode Open Food Facts does not know', async () => {
    const { fetchMock, user } = renderScan({ 'GET /api/products/lookup': NOT_FOUND });
    await typeBarcode(user);
    await screen.findByTestId(testIds.scanNotice);
    // One way back to the scanner, not two.
    expect(screen.getAllByRole('button', { name: /^Scan/ })).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: 'Scan again' }));

    expect(await screen.findByRole('textbox', { name: 'Barcode' })).toHaveValue('');
    expect(screen.queryByTestId(testIds.scanNotice)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.scanWhich)).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, 'GET /api/products/lookup')).toHaveLength(1);
  });

  it('starts over with another barcode', async () => {
    const { user } = renderScan();
    await typeBarcode(user);
    await screen.findByTestId(testIds.scanProposal);

    await user.click(screen.getByRole('button', { name: 'Scan another barcode' }));

    expect(await screen.findByRole('textbox', { name: 'Barcode' })).toHaveValue('');
    expect(screen.queryByTestId(testIds.scanProposal)).not.toBeInTheDocument();
  });
});
