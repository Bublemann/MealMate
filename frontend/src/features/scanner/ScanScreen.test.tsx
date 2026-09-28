import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { errorResponse, mockApi, requestsTo } from '@/test/api';
import { APPLES, ingredient, proposal, REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { loadDecoder } from './decoder';

type Schemas = components['schemas'];

// jsdom has no camera, so the scanner shows its manual input: the path E2E and people without a
// camera take (BAR-01). The decoder itself is tested in decoder.test.ts.
vi.mock('./decoder', () => ({ loadDecoder: vi.fn(), decodeVideoFrame: vi.fn() }));

const BARCODE = '4006381333931';
const PROPOSAL = proposal();
const LOOKUP = '/api/ingredients/lookup';

function lookup(overrides: Partial<Schemas['BarcodeLookup']> = {}): Schemas['BarcodeLookup'] {
  return {
    barcode: BARCODE,
    found_in: 'off',
    ingredient: null,
    proposal: PROPOSAL,
    off_unavailable: false,
    ...overrides,
  };
}

const NOT_FOUND = lookup({ found_in: 'none', proposal: null });

/** The server's answer to a create: the ingredient as sent, with an id. */
function created(request: Request) {
  return request.json().then((body: Schemas['IngredientCreate']) =>
    Response.json(
      ingredient({
        id: 'ing-created',
        name: body.name,
        brand: body.brand ?? null,
        barcode: body.barcode ?? null,
        source: body.off ? 'off' : 'manual',
      }),
      { status: 201 },
    ),
  );
}

function renderScan(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    [`GET ${LOOKUP}`]: lookup(),
    'GET /api/ingredients/similar': [],
    'GET /api/ingredients': [summary('Milch', 'dairy_eggs', { base_unit: 'ml' })],
    'POST /api/ingredients': created,
    'GET /api/ingredients/ing-created': ingredient({ id: 'ing-created', name: 'Created' }),
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
      [`GET ${LOOKUP}`]: lookup({ found_in: 'db', ingredient: APPLES, proposal: null }),
      'GET /api/ingredients/ing-aepfel': APPLES,
    });

    await typeBarcode(user, '4006 3813 33931');

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-aepfel'));
    const [request] = requestsTo(fetchMock, `GET ${LOOKUP}`);
    expect(new URL(request?.url ?? '').searchParams.get('barcode')).toBe(BARCODE);
  });

  it('opens the ingredient form filled from Open Food Facts, as text (BAR-03, BAR-09)', async () => {
    const { user } = renderScan({
      [`GET ${LOOKUP}`]: lookup({ proposal: { ...PROPOSAL, name: '<b>Milch</b>' } }),
    });

    await typeBarcode(user);

    expect(await screen.findByRole('heading', { name: 'Found at Open Food Facts' })).toHaveFocus();
    const form = screen.getByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Name')).toHaveValue('<b>Milch</b>');
    expect(within(form).getByLabelText('Brand')).toHaveValue('Weidehof');
    await waitFor(() =>
      expect(within(form).getByLabelText('Category')).toHaveValue('cat-dairy_eggs'),
    );
    expect(within(form).getByRole('radio', { name: 'Millilitres (ml)' })).toBeChecked();
    expect(
      within(form).getByRole('group', { name: 'Nutrition per 100 ml (optional)' }),
    ).toBeVisible();
    expect(within(form).getByLabelText('Calories')).toHaveValue('64');
    expect(within(form).getByLabelText('Fat')).toHaveValue('3.5');
    expect(within(form).getByLabelText('Barcode')).toHaveValue(BARCODE);
    expect(within(form).getByLabelText('Barcode')).toHaveAttribute('readonly');
    expect(within(form).getByLabelText('Package size as printed')).toHaveValue('1 l');
    expect(within(form).getByLabelText('Unit of the contents')).toHaveValue('l');
    const link = within(form).getByRole('link', { name: /^Open Food Facts/ });
    expect(link).toHaveAttribute('href', 'https://world.openfoodfacts.org');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link).toHaveAttribute('target', '_blank');
    // No step in between: no "which ingredient is this?", no search from here.
    expect(within(form).queryByTestId(testIds.offSearchButton)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.scanNotice)).not.toBeInTheDocument();
  });

  it('saves the scanned product with one tap and one request, marking corrected fields (BAR-04)', async () => {
    const { fetchMock, router, user } = renderScan();
    await typeBarcode(user);

    const form = await screen.findByTestId(testIds.ingredientForm);
    await user.clear(within(form).getByLabelText('Name'));
    await user.type(within(form).getByLabelText('Name'), 'Vollmilch');
    const kcal = within(form).getByLabelText('Calories');
    await user.clear(kcal);
    await user.type(kcal, '65');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-created'));
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(1);
    expect(await bodyOf(fetchMock, 'POST /api/ingredients')).toEqual({
      name: 'Vollmilch',
      base_unit: 'ml',
      category_id: 'cat-dairy_eggs',
      brand: 'Weidehof',
      barcode: BARCODE,
      quantity_text: '1 l',
      pack_quantity: 1,
      pack_unit: 'l',
      nutrients: { kcal: 65, protein: 3.4, carbs: 4.8, sugar: 4.8, fat: 3.5 },
      off: {
        off_last_modified_at: '2026-09-01T10:00:00Z',
        edited_fields: ['name', 'nutrients.kcal'],
      },
    });
  });

  it('cuts a long Open Food Facts name at a word to fit the name field', async () => {
    const { user } = renderScan({
      [`GET ${LOOKUP}`]: lookup({
        proposal: {
          ...PROPOSAL,
          name: 'Frische fettarme Milch aus der Region, länger haltbar, homogenisiert, 1,5 % Fett',
        },
      }),
    });
    await typeBarcode(user);

    const form = await screen.findByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Name')).toHaveValue(
      'Frische fettarme Milch aus der Region, länger haltbar,',
    );
  });

  it('never shows a negative zero from Open Food Facts as "-0"', async () => {
    // JSON can carry `-0`, and Intl.NumberFormat shows it with its sign.
    const zeros = lookup({
      proposal: { ...PROPOSAL, nutrients: { ...PROPOSAL.nutrients, fat: 0 } },
    });
    const text = JSON.stringify(zeros).replace('"fat":0', '"fat":-0');
    expect(text).toContain('"fat":-0');
    const { user } = renderScan({
      [`GET ${LOOKUP}`]: new Response(text, { headers: { 'Content-Type': 'application/json' } }),
    });
    await typeBarcode(user);

    const form = await screen.findByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Fat')).toHaveValue('0');
  });

  it('opens the form with only the barcode when Open Food Facts does not know it', async () => {
    const { fetchMock, router, user } = renderScan({ [`GET ${LOOKUP}`]: NOT_FOUND });
    await typeBarcode(user);

    // The barcode looked up shows, so that a misread code can be seen.
    expect(await screen.findByTestId(testIds.scanNotice)).toHaveTextContent(
      `Not found (${BARCODE}) – enter the values yourself.`,
    );
    expect(screen.getByRole('heading', { name: 'New ingredient' })).toHaveFocus();
    const form = screen.getByTestId(testIds.ingredientForm);
    expect(within(form).queryByTestId(testIds.offAttribution)).not.toBeInTheDocument();
    expect(within(form).getByLabelText('Name')).toHaveValue('');
    expect(within(form).getByLabelText('Barcode')).toHaveValue(BARCODE);
    expect(within(form).getByLabelText('Barcode')).not.toHaveAttribute('readonly');
    await user.type(within(form).getByLabelText('Name'), 'Hafermilch');
    await user.type(within(form).getByLabelText('Calories'), '46');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-created'));
    expect(await bodyOf(fetchMock, 'POST /api/ingredients')).toEqual({
      name: 'Hafermilch',
      base_unit: 'g',
      category_id: 'cat-other',
      barcode: BARCODE,
      nutrients: { kcal: 46 },
    });
  });

  it('says when Open Food Facts could not be asked and tries again on request', async () => {
    let answers = 0;
    const { user } = renderScan({
      [`GET ${LOOKUP}`]: () => {
        answers += 1;
        return answers === 1 ? { ...NOT_FOUND, off_unavailable: true } : lookup();
      },
    });
    await typeBarcode(user);

    expect(await screen.findByTestId(testIds.scanNotice)).toHaveTextContent(
      `Open Food Facts is slow (${BARCODE}) – try again or enter the values yourself.`,
    );
    // The values can be entered right away …
    const form = screen.getByTestId(testIds.ingredientForm);
    await user.type(within(form).getByLabelText('Name'), 'Milch');
    // … or Open Food Facts asked again, which fills the form.
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Found at Open Food Facts' })).toBeVisible();
    expect(screen.getByLabelText('Name')).toHaveValue('Frische Vollmilch 3,5 %');
  });

  it('offers to try again or enter the values when Open Food Facts is busy', async () => {
    const { user } = renderScan({ [`GET ${LOOKUP}`]: errorResponse(503, 'off.busy') });
    await typeBarcode(user);

    expect(await screen.findByTestId(testIds.scanNotice)).toHaveTextContent(
      `Open Food Facts is slow (${BARCODE})`,
    );
    expect(screen.getByTestId(testIds.scanAgain)).toHaveTextContent('Scan again');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeVisible();
    await user.click(screen.getByTestId(testIds.scanEnterManually));

    const form = await screen.findByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Name')).toHaveValue('');
    expect(within(form).getByLabelText('Barcode')).toHaveValue(BARCODE);
  });

  it('gives a lookup 25 s before it counts as slow (plan § 8)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockApi({ ...REFERENCE_ROUTES });
    // A lookup that never answers, until the client gives up.
    vi.stubGlobal('fetch', (request: Request, init?: RequestInit) => {
      if (new URL(request.url).pathname !== LOOKUP) return fetchMock(request);
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
      [`GET ${LOOKUP}`]: errorResponse(422, 'common.validation', [
        { loc: ['query', 'barcode'], code: 'invalid_format' },
      ]),
    });
    await typeBarcode(user, '4006381333932');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "4006381333932 isn't a valid barcode. Please check the digits.",
    );
    expect(screen.getByRole('textbox', { name: 'Barcode' })).toBeVisible();
  });

  it.each([
    ['not found', NOT_FOUND],
    ['Open Food Facts slow', { ...NOT_FOUND, off_unavailable: true }],
  ])('scans again straight from the notice (%s)', async (_case, answer) => {
    const { fetchMock, user } = renderScan({ [`GET ${LOOKUP}`]: answer });
    await typeBarcode(user);
    await screen.findByTestId(testIds.scanNotice);
    // One way back to the scanner, not two.
    expect(screen.getAllByRole('button', { name: /^Scan (again|another)/ })).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: 'Scan again' }));

    expect(await screen.findByRole('textbox', { name: 'Barcode' })).toHaveValue('');
    expect(screen.queryByTestId(testIds.scanNotice)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.ingredientForm)).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, `GET ${LOOKUP}`)).toHaveLength(1);
  });

  it('starts over with another barcode', async () => {
    const { user } = renderScan();
    await typeBarcode(user);
    await screen.findByTestId(testIds.ingredientForm);

    await user.click(screen.getByRole('button', { name: 'Scan another barcode' }));

    expect(await screen.findByRole('textbox', { name: 'Barcode' })).toHaveValue('');
    expect(screen.queryByTestId(testIds.ingredientForm)).not.toBeInTheDocument();
  });

  describe('"This is already in MealMate"', () => {
    const ONIONS = summary('Zwiebeln', 'fruit_vegetables');
    const BRANDED = summary('Zwiebelschmalz', 'other', {
      brand: 'Hofgut',
      barcode: '4000000000006',
    });

    const LINK = 'POST /api/ingredients/ing-zwiebeln/barcode';

    function renderLink(routes: Record<string, unknown> = {}) {
      return renderScan({
        'GET /api/ingredients': [ONIONS, BRANDED],
        [LINK]: ingredient({ ...ONIONS, id: 'ing-zwiebeln', barcode: BARCODE }),
        'GET /api/ingredients/ing-zwiebeln': ingredient({ ...ONIONS, barcode: BARCODE }),
        ...routes,
      });
    }

    it('gives the barcode to an ingredient without one', async () => {
      const { fetchMock, router, user } = renderLink();
      await typeBarcode(user);
      await user.click(await screen.findByTestId(testIds.scanLinkExisting));

      const link = await screen.findByTestId(testIds.scanLink);
      expect(
        within(link).getByRole('heading', { name: 'Add the barcode to an ingredient' }),
      ).toHaveFocus();
      await user.type(within(link).getByLabelText('Search ingredient'), 'Zwiebel');
      await user.click(await within(link).findByRole('button', { name: /^Zwiebeln/ }));

      await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-zwiebeln'));
      // Its own request, which never replaces a barcode (not the edit form's PATCH).
      expect(await bodyOf(fetchMock, LINK)).toEqual({ barcode: BARCODE });
      expect(requestsTo(fetchMock, 'PATCH /api/ingredients/ing-zwiebeln')).toHaveLength(0);
      expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
    });

    it.each([
      [
        'ingredient.has_barcode',
        'This ingredient already has a barcode. Another package or brand is another ingredient',
      ],
      ['ingredient.barcode_taken', 'Another ingredient already has this barcode.'],
    ])('says why the server refused (%s), e.g. after a change elsewhere', async (code, text) => {
      const { fetchMock, router, user } = renderLink({ [LINK]: errorResponse(409, code) });
      await typeBarcode(user);
      await user.click(await screen.findByTestId(testIds.scanLinkExisting));

      const link = await screen.findByTestId(testIds.scanLink);
      await user.type(within(link).getByLabelText('Search ingredient'), 'Zwiebel');
      await user.click(await within(link).findByRole('button', { name: /^Zwiebeln/ }));

      expect(await within(link).findByRole('alert')).toHaveTextContent(text);
      expect(requestsTo(fetchMock, LINK)).toHaveLength(1);
      expect(router.state.location.pathname).toBe('/scan');
    });

    it('refuses an ingredient that has a barcode already, and goes back to the form', async () => {
      const { fetchMock, user } = renderLink();
      await typeBarcode(user);
      await user.click(await screen.findByTestId(testIds.scanLinkExisting));

      const link = await screen.findByTestId(testIds.scanLink);
      await user.type(within(link).getByLabelText('Search ingredient'), 'Zwiebel');
      await user.click(
        await within(link).findByRole('button', {
          name: /^Zwiebelschmalz \(Hofgut\) with barcode/,
        }),
      );

      expect(await within(link).findByRole('alert')).toHaveTextContent(
        'Zwiebelschmalz (Hofgut) already has a barcode.',
      );
      expect(
        requestsTo(fetchMock, 'POST /api/ingredients/ing-zwiebelschmalz/barcode'),
      ).toHaveLength(0);
      await user.click(within(link).getByRole('button', { name: 'Back to the form' }));
      expect(await screen.findByTestId(testIds.ingredientForm)).toBeVisible();
    });
  });
});
