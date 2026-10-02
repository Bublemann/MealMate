import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BEN, errorResponse, mockApi, nodeFormClasses, requestsTo } from '@/test/api';
import { bareMeal, CUISINES, EGGS, FLOUR, meal, MEAL_ROUTES, MILK, SALT } from '@/test/meals';
import { LIST_ID, listDetail } from '@/test/lists';
import { ingredient, proposal } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const INGREDIENTS = [FLOUR, MILK, EGGS, SALT];

// The scanner's decoder needs a browser; jsdom has no camera anyway, so the scanner shows its
// manual input (see features/scanner for its own tests).
vi.mock('@/features/scanner/decoder', () => ({
  loadDecoder: () => Promise.resolve(),
  decodeVideoFrame: () => Promise.resolve(null),
}));

function searchIngredients(request: Request) {
  const q = new URL(request.url).searchParams.get('q')?.toLowerCase() ?? '';
  return INGREDIENTS.filter((ingredient) => ingredient.name.toLowerCase().startsWith(q));
}

function renderForm(path: string, routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...MEAL_ROUTES,
    'GET /api/ingredients': searchIngredients,
    'GET /api/meals': [],
    ...routes,
  });
  return { fetchMock, ...renderApp(path) };
}

async function bodyOf(fetchMock: ReturnType<typeof mockApi>, route: string, index = 0) {
  const request = requestsTo(fetchMock, route)[index];
  if (!request) throw new Error(`no request to ${route}`);
  return (await request.json()) as unknown;
}

/** Draw calls of the photo preview canvas. */
let drawImage: ReturnType<typeof vi.fn>;

beforeEach(() => {
  // jsdom can't decode images or draw on a canvas: the photo preview gets fakes of both.
  drawImage = vi.fn();
  vi.stubGlobal(
    'createImageBitmap',
    vi.fn().mockResolvedValue({ width: 1600, height: 1200, close: vi.fn() }),
  );
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () => ({ drawImage }) as unknown as CanvasRenderingContext2D,
  );
});

/** A photo the (stubbed) FormData can send; see nodeFormClasses. */
async function photoFile(name: string, type: string): Promise<File> {
  const node = await nodeFormClasses();
  vi.stubGlobal('FormData', node.FormData);
  return new node.File(['image-bytes'], name, { type });
}

type User = ReturnType<typeof renderApp>['user'];

async function addIngredient(user: User, name: string) {
  const form = screen.getByTestId(testIds.mealForm);
  const picker = within(form).getByTestId(testIds.ingredientPicker);
  await user.type(within(picker).getByLabelText('Add ingredient'), name);
  await user.click(await within(picker).findByRole('button', { name: new RegExp(`^${name}`) }));
}

function row(name: string): HTMLElement {
  return screen.getByRole('listitem', { name: `Ingredient ${name}` });
}

describe('MealFormScreen (create)', () => {
  // The longest walk through the form (typing every field, then the upload): under a busy
  // test machine it can take more than the default 5 s.
  it('creates a meal with rows, tags and cuisine, then uploads the photo', async () => {
    const created = meal({ id: 'meal-new', photo: null });
    const { fetchMock, user, router } = renderForm('/meals/new', {
      'POST /api/meals': Response.json(created, { status: 201 }),
      'PUT /api/meals/meal-new/photo': meal({ id: 'meal-new' }),
      'GET /api/meals/meal-new': meal({ id: 'meal-new' }),
    });
    const form = await screen.findByTestId(testIds.mealForm);

    await user.type(within(form).getByLabelText('Name'), '  Pfannkuchen ');
    await user.click(within(form).getByRole('button', { name: 'More servings' }));
    await user.click(within(form).getByRole('button', { name: 'More servings' }));
    await user.click(within(form).getByRole('button', { name: 'Fewer servings' }));
    expect(within(form).getByLabelText('Servings')).toHaveValue('2');
    await waitFor(() =>
      expect(within(form).getByRole('option', { name: 'German' })).toBeInTheDocument(),
    );
    await user.selectOptions(within(form).getByLabelText('Cuisine'), 'German');

    // A typed tag (Enter adds it, it doesn't submit) and a suggested one.
    await user.type(within(form).getByLabelText('Tags'), 'Frühstück{Enter}');
    await user.type(within(form).getByLabelText('Tags'), 'schn');
    await user.click(await within(form).findByRole('button', { name: 'Add tag “schnell”' }));
    await user.type(within(form).getByLabelText('Tags'), 'frühstück{Enter}');
    expect(within(form).getByRole('list', { name: 'Tags of this meal' })).toHaveTextContent(
      'Frühstückschnell',
    );

    await addIngredient(user, 'Mehl');
    await addIngredient(user, 'Milch');
    await addIngredient(user, 'Salz');
    // Typing an amount picks the base unit.
    await user.type(within(row('Mehl')).getByLabelText('Amount'), '200');
    expect(within(row('Mehl')).getByLabelText('Unit')).toHaveDisplayValue('g');
    await user.type(within(row('Milch')).getByLabelText('Amount'), '0,3');
    await user.selectOptions(within(row('Milch')).getByLabelText('Unit'), 'l');
    await user.type(within(row('Salz')).getByLabelText('Note'), ' to taste ');
    // Salz moves to the top, then Milch is removed.
    await user.click(within(row('Salz')).getByRole('button', { name: 'Move Salz up' }));
    await user.click(within(row('Salz')).getByRole('button', { name: 'Move Salz up' }));
    expect(within(row('Salz')).getByRole('button', { name: 'Move Salz up' })).toBeDisabled();
    await user.click(within(row('Milch')).getByRole('button', { name: 'Remove Milch' }));
    await addIngredient(user, 'Milch');
    await user.type(within(row('Milch')).getByLabelText('Amount'), '0,3');
    await user.selectOptions(within(row('Milch')).getByLabelText('Unit'), 'l');
    expect(
      within(form)
        .getAllByTestId(testIds.mealIngredientRow)
        .map((item) => item.getAttribute('aria-label')),
    ).toEqual(['Ingredient Salz', 'Ingredient Mehl', 'Ingredient Milch']);

    await user.type(within(form).getByLabelText('Instructions'), 'Verrühren.{Enter}Backen.');
    await user.type(within(form).getByLabelText('Source link'), 'https://example.org/p');
    const photo = await photoFile('dish.png', 'image/png');
    await user.upload(within(form).getByTestId(testIds.mealPhotoInput), photo);
    // The preview is drawn onto a canvas; the file never becomes a URL on the page.
    const preview = within(form).getByRole('img', { name: 'Pfannkuchen' });
    expect(preview.tagName).toBe('CANVAS');
    expect(preview).not.toHaveAttribute('src');
    await waitFor(() => expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 800, 600));

    await user.click(within(form).getByRole('button', { name: 'Create meal' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-new'));
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(1);
    await expect(bodyOf(fetchMock, 'POST /api/meals')).resolves.toEqual({
      name: 'Pfannkuchen',
      servings: 2,
      instructions: 'Verrühren.\nBacken.',
      source_url: 'https://example.org/p',
      cuisine_id: 'cui-german',
      tags: ['Frühstück', 'schnell'],
      ingredients: [
        { ingredient_id: SALT.id, amount: null, unit: null, note: 'to taste' },
        { ingredient_id: FLOUR.id, amount: 200, unit: 'g', note: null },
        { ingredient_id: MILK.id, amount: 0.3, unit: 'l', note: null },
      ],
    });
    // The photo goes up after the meal is saved, as multipart field `file`.
    const [upload] = requestsTo(fetchMock, 'PUT /api/meals/meal-new/photo');
    expect(upload?.headers.get('content-type')).toMatch(/^multipart\/form-data; boundary=/);
    expect(upload?.headers.get('authorization')).toBe('Bearer test-access-token');
    expect(await upload?.text()).toMatch(/name="file"; filename="dish\.png"/);
  }, 15_000);

  it('adds the ingredient of a scanned product as a row (BAR-01)', async () => {
    const { fetchMock, user } = renderForm('/meals/new', {
      'GET /api/ingredients/lookup': {
        barcode: '4006381333931',
        found_in: 'db',
        ingredient: ingredient({ ...MILK, brand: 'Weidehof', barcode: '4006381333931' }),
        proposal: null,
        off_unavailable: false,
      },
    });
    const form = await screen.findByTestId(testIds.mealForm);
    await user.type(within(form).getByLabelText('Name'), 'Kakao');

    await user.click(within(form).getByRole('button', { name: 'Scan barcode' }));
    const dialog = await screen.findByTestId(testIds.scanDialog);
    expect(dialog).toHaveAccessibleName('Scan barcode');
    await user.type(within(dialog).getByRole('textbox', { name: 'Barcode' }), '4006381333931');
    await user.click(within(dialog).getByRole('button', { name: 'Look up' }));

    expect(
      await within(form).findByRole('listitem', { name: 'Ingredient Milch (Weidehof)' }),
    ).toBeVisible();
    await waitFor(() => expect(screen.queryByTestId(testIds.scanDialog)).not.toBeInTheDocument());
    // The meal isn't saved by the scanner's form.
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(0);
    expect(within(form).getByLabelText('Name')).toHaveValue('Kakao');
  });

  it('creates the ingredient of a new scanned product in the dialog and adds it (BAR-03)', async () => {
    const created = ingredient({
      id: 'ing-kakao',
      name: 'Kakaopulver',
      brand: 'Bio',
      barcode: '4006381333931',
      source: 'off',
    });
    const { fetchMock, user } = renderForm('/meals/new', {
      'GET /api/ingredients/lookup': {
        barcode: '4006381333931',
        found_in: 'off',
        ingredient: null,
        proposal: proposal({ name: 'Kakaopulver', brand: 'Bio', nutrition_basis: 'g' }),
        off_unavailable: false,
      },
      'GET /api/ingredients/similar': [],
      'POST /api/ingredients': Response.json(created, { status: 201 }),
    });
    const form = await screen.findByTestId(testIds.mealForm);
    await user.type(within(form).getByLabelText('Name'), 'Kakao');

    await user.click(within(form).getByRole('button', { name: 'Scan barcode' }));
    const dialog = await screen.findByTestId(testIds.scanDialog);
    await user.type(within(dialog).getByRole('textbox', { name: 'Barcode' }), '4006381333931');
    await user.click(within(dialog).getByRole('button', { name: 'Look up' }));
    const ingredientForm = await within(dialog).findByTestId(testIds.ingredientForm);
    expect(within(ingredientForm).getByLabelText('Name')).toHaveValue('Kakaopulver');
    await user.click(within(ingredientForm).getByRole('button', { name: 'Save' }));

    expect(
      await within(form).findByRole('listitem', { name: 'Ingredient Kakaopulver (Bio)' }),
    ).toBeVisible();
    await waitFor(() => expect(screen.queryByTestId(testIds.scanDialog)).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(1);
    // Saving the ingredient doesn't save the meal.
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(0);
  });

  it('searches Open Food Facts with Enter from the picker, without saving the meal', async () => {
    const { fetchMock, user } = renderForm('/meals/new', {
      'GET /api/ingredients/similar': [],
      'GET /api/ingredients/off-search': { q: 'Kakao', page: 1, results: [], has_more: false },
    });
    const form = await screen.findByTestId(testIds.mealForm);
    await user.type(within(form).getByLabelText('Name'), 'Kakao');
    await user.type(within(form).getByLabelText('Add ingredient'), 'Kakao');
    await user.click(await within(form).findByTestId(testIds.ingredientPickerCreate));
    await user.click(await screen.findByTestId(testIds.offSearchButton));
    const search = await screen.findByTestId(testIds.offSearchDialog);

    await user.type(within(search).getByLabelText('Product name or brand'), '{Enter}');

    expect(await within(search).findByTestId(testIds.offSearchEmpty)).toBeVisible();
    expect(requestsTo(fetchMock, 'GET /api/ingredients/off-search')).toHaveLength(1);
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(0);
  });

  it('fills in the name searched for on the Meals tab (MEAL-09)', async () => {
    const created = bareMeal({ name: 'Lasagne al forno' });
    const { fetchMock, user, router } = renderForm('/meals/new?name=%20Lasagne%20al%20forno%20', {
      'POST /api/meals': Response.json(created, { status: 201 }),
    });
    const form = await screen.findByTestId(testIds.mealForm);

    expect(screen.getByRole('heading', { level: 1, name: 'New meal' })).toBeVisible();
    expect(within(form).getByLabelText('Name')).toHaveValue('Lasagne al forno');
    await user.click(within(form).getByRole('button', { name: 'Create meal' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-new'));
    await expect(bodyOf(fetchMock, 'POST /api/meals')).resolves.toMatchObject({
      name: 'Lasagne al forno',
    });
  });

  it('keeps servings between 1 and 99', async () => {
    const { fetchMock, user } = renderForm('/meals/new');
    const form = await screen.findByTestId(testIds.mealForm);
    const servings = within(form).getByLabelText('Servings');

    expect(servings).toHaveValue('1');
    expect(within(form).getByRole('button', { name: 'Fewer servings' })).toBeDisabled();
    await user.clear(servings);
    await user.type(servings, '99');
    expect(within(form).getByRole('button', { name: 'More servings' })).toBeDisabled();
    await user.clear(servings);
    await user.type(servings, 'x0');
    expect(servings).toHaveValue('0');
    await user.type(within(form).getByLabelText('Name'), 'Suppe');
    await user.click(within(form).getByRole('button', { name: 'Create meal' }));

    expect(servings).toHaveAccessibleDescription(/^Out of range/);
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(0);
  });

  it('refuses an amount it cannot read without asking the server', async () => {
    const { fetchMock, user } = renderForm('/meals/new');
    await screen.findByTestId(testIds.mealForm);

    await user.type(screen.getByLabelText('Name'), 'Suppe');
    await addIngredient(user, 'Mehl');
    await user.type(within(row('Mehl')).getByLabelText('Amount'), '1,2,3');
    await user.click(screen.getByRole('button', { name: 'Create meal' }));

    expect(within(row('Mehl')).getByLabelText('Amount')).toHaveAccessibleDescription(
      'Invalid format',
    );
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(0);
  });

  it('takes a picked unit back when the amount is cleared', async () => {
    const { fetchMock, user } = renderForm('/meals/new', {
      'POST /api/meals': Response.json(bareMeal(), { status: 201 }),
      'GET /api/meals/meal-new': bareMeal(),
    });
    await screen.findByTestId(testIds.mealForm);

    await user.type(screen.getByLabelText('Name'), 'Suppe');
    await addIngredient(user, 'Milch');
    const amount = within(row('Milch')).getByLabelText('Amount');
    const unit = within(row('Milch')).getByLabelText('Unit');
    await user.type(amount, '300');
    expect(unit).toHaveDisplayValue('ml');
    await user.clear(amount);
    expect(unit).toHaveDisplayValue('No unit');
    await user.click(screen.getByRole('button', { name: 'Create meal' }));

    await expect(bodyOf(fetchMock, 'POST /api/meals')).resolves.toMatchObject({
      ingredients: [{ ingredient_id: MILK.id, amount: null, unit: null, note: null }],
    });
  });

  it('clears its own row errors once rows move or are removed', async () => {
    const { fetchMock, user } = renderForm('/meals/new');
    await screen.findByTestId(testIds.mealForm);
    await user.type(screen.getByLabelText('Name'), 'Suppe');
    await addIngredient(user, 'Mehl');
    await addIngredient(user, 'Milch');
    await addIngredient(user, 'Salz');
    const amountOf = (name: string) => within(row(name)).getByLabelText('Amount');

    await user.type(amountOf('Milch'), '1,2,3');
    await user.click(screen.getByRole('button', { name: 'Create meal' }));
    expect(amountOf('Milch')).toHaveAccessibleDescription('Invalid format');
    // Typing elsewhere keeps the error where it is.
    await user.type(amountOf('Salz'), '1');
    expect(amountOf('Milch')).toHaveAccessibleDescription('Invalid format');

    await user.click(within(row('Milch')).getByRole('button', { name: 'Move Milch up' }));
    for (const name of ['Mehl', 'Milch', 'Salz']) {
      expect(amountOf(name)).not.toHaveAccessibleDescription();
    }

    await user.click(screen.getByRole('button', { name: 'Create meal' }));
    expect(amountOf('Milch')).toHaveAccessibleDescription('Invalid format');
    await user.click(within(row('Milch')).getByRole('button', { name: 'Remove Milch' }));
    for (const name of ['Mehl', 'Salz']) {
      expect(amountOf(name)).not.toHaveAccessibleDescription();
    }
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(0);
  });

  it('shows the server errors next to the row and field they belong to', async () => {
    const { fetchMock, user } = renderForm('/meals/new', {
      'POST /api/meals': errorResponse(422, 'common.validation', [
        { loc: ['body', 'ingredients', 0, 'amount'], code: 'required' },
        { loc: ['body', 'source_url'], code: 'invalid_format' },
        { loc: ['body', 'tags', 1], code: 'too_long' },
      ]),
    });
    await screen.findByTestId(testIds.mealForm);

    await user.type(screen.getByLabelText('Name'), 'Suppe');
    await addIngredient(user, 'Salz');
    // A unit without an amount: the server refuses it.
    await user.selectOptions(within(row('Salz')).getByLabelText('Unit'), 'tsp');
    await user.type(screen.getByLabelText('Source link'), 'ftp://example.org');
    await user.click(screen.getByRole('button', { name: 'Create meal' }));

    await waitFor(() =>
      expect(within(row('Salz')).getByLabelText('Amount')).toHaveAccessibleDescription('Required'),
    );
    expect(screen.getByLabelText('Source link')).toHaveAccessibleDescription(/^Invalid format/);
    expect(screen.getByLabelText('Tags')).toHaveAccessibleDescription(/^Too long/);
    expect(screen.queryByText('Please check your input.')).not.toBeInTheDocument();
    await expect(bodyOf(fetchMock, 'POST /api/meals')).resolves.toMatchObject({
      ingredients: [{ ingredient_id: SALT.id, amount: null, unit: 'tsp', note: null }],
    });
  });

  it('adds a cuisine inline and selects it', async () => {
    const added = { id: 'cui-new', key: null, name: 'Fränkisch' };
    let cuisines = CUISINES;
    const { fetchMock, user } = renderForm('/meals/new', {
      'GET /api/cuisines': () => cuisines,
      'POST /api/cuisines': () => {
        cuisines = [...CUISINES, added];
        return Response.json(added, { status: 201 });
      },
    });
    const form = await screen.findByTestId(testIds.mealForm);

    await user.click(within(form).getByRole('button', { name: 'Add cuisine…' }));
    await user.type(within(form).getByLabelText('New cuisine'), 'Fränkisch{Enter}');

    await waitFor(() =>
      expect(within(form).getByLabelText('Cuisine')).toHaveDisplayValue('Fränkisch'),
    );
    await expect(bodyOf(fetchMock, 'POST /api/cuisines')).resolves.toEqual({ name: 'Fränkisch' });
    expect(requestsTo(fetchMock, 'POST /api/meals')).toHaveLength(0);
  });

  it('allows at most 10 tags', async () => {
    const { user } = renderForm('/meals/new');
    const form = await screen.findByTestId(testIds.mealForm);
    const input = within(form).getByLabelText('Tags');

    for (let i = 1; i <= 10; i += 1) await user.type(input, `t${i}{Enter}`);

    expect(input).toBeDisabled();
    expect(input).toHaveAccessibleDescription("That's 10 tags. Remove one to add another.");
    await user.click(within(form).getByRole('button', { name: 'Remove tag t3' }));
    expect(input).toBeEnabled();
    expect(within(form).getByRole('list', { name: 'Tags of this meal' }).children).toHaveLength(9);
  });

  it('keeps the meal when the photo upload fails and says so on the detail', async () => {
    const created = bareMeal({ name: 'Suppe' });
    const { user, router } = renderForm('/meals/new', {
      'POST /api/meals': Response.json(created, { status: 201 }),
      'PUT /api/meals/meal-new/photo': errorResponse(413, 'media.too_large'),
      'GET /api/meals/meal-new': created,
    });
    const form = await screen.findByTestId(testIds.mealForm);

    await user.type(within(form).getByLabelText('Name'), 'Suppe');
    await user.upload(
      within(form).getByTestId(testIds.mealPhotoInput),
      await photoFile('big.jpg', 'image/jpeg'),
    );
    await user.click(within(form).getByRole('button', { name: 'Create meal' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-new'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "The meal is saved, but the photo wasn't: The photo is too big (at most 10 MB).",
    );
  });

  it('says a photo is chosen when the browser cannot show a preview', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new DOMException('bad')));
    const { user } = renderForm('/meals/new', {});
    const form = await screen.findByTestId(testIds.mealForm);

    await user.upload(
      within(form).getByTestId(testIds.mealPhotoInput),
      await photoFile('odd.webp', 'image/webp'),
    );

    expect(
      await within(form).findByText("Photo chosen. The preview isn't available in this browser."),
    ).toBeInTheDocument();
    expect(within(form).queryByRole('img')).not.toBeInTheDocument();
    expect(within(form).getByRole('button', { name: 'Remove photo' })).toBeInTheDocument();
  });
});

describe('MealFormScreen (edit)', () => {
  it('fills in the meal and sends only what changed', async () => {
    const original = meal();
    const { fetchMock, user, router } = renderForm('/meals/meal-pancakes/edit', {
      'GET /api/meals/meal-pancakes': original,
      'PATCH /api/meals/meal-pancakes': meal({ servings: 3 }),
    });
    const form = await screen.findByTestId(testIds.mealForm);

    expect(screen.getByRole('heading', { level: 1, name: 'Edit Pfannkuchen' })).toBeVisible();
    expect(within(form).getByLabelText('Name')).toHaveValue('Pfannkuchen');
    expect(within(form).getByLabelText('Servings')).toHaveValue('2');
    expect(within(row('Eier')).getByLabelText('Amount')).toHaveValue('2');
    expect(within(row('Eier')).getByLabelText('Unit')).toHaveDisplayValue('pcs');
    expect(within(row('Eier')).getByLabelText('Note')).toHaveValue('Größe M');
    expect(within(form).getByRole('img', { name: 'Pfannkuchen' })).toHaveAttribute(
      'src',
      '/api/media/abc.webp?exp=1&sig=x',
    );

    await user.click(within(form).getByRole('button', { name: 'More servings' }));
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-pancakes'));
    await expect(bodyOf(fetchMock, 'PATCH /api/meals/meal-pancakes')).resolves.toEqual({
      servings: 3,
    });
    expect(requestsTo(fetchMock, 'PUT /api/meals/meal-pancakes/photo')).toHaveLength(0);
  });

  it('sends the whole row list when a row changes, clears fields and removes the photo', async () => {
    const { fetchMock, user } = renderForm('/meals/meal-pancakes/edit', {
      'GET /api/meals/meal-pancakes': meal(),
      'PATCH /api/meals/meal-pancakes': meal(),
      'DELETE /api/meals/meal-pancakes/photo': null,
    });
    const form = await screen.findByTestId(testIds.mealForm);

    await user.clear(within(row('Mehl')).getByLabelText('Amount'));
    await user.type(within(row('Mehl')).getByLabelText('Amount'), '250');
    await user.clear(within(form).getByLabelText('Source link'));
    await user.selectOptions(within(form).getByLabelText('Cuisine'), 'No cuisine');
    await user.click(within(form).getByRole('button', { name: 'Remove tag schnell' }));
    await user.click(within(form).getByRole('button', { name: 'Remove photo' }));
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'DELETE /api/meals/meal-pancakes/photo')).toHaveLength(1),
    );
    await expect(bodyOf(fetchMock, 'PATCH /api/meals/meal-pancakes')).resolves.toEqual({
      source_url: null,
      cuisine_id: null,
      tags: [],
      ingredients: [
        { ingredient_id: FLOUR.id, amount: 250, unit: 'g', note: null },
        { ingredient_id: MILK.id, amount: 300, unit: 'ml', note: null },
        { ingredient_id: EGGS.id, amount: 2, unit: 'piece', note: 'Größe M' },
        { ingredient_id: SALT.id, amount: null, unit: null, note: 'to taste' },
      ],
    });
  });

  it('picks the base unit when an amount is typed into a loaded "to taste" row', async () => {
    const { fetchMock, user } = renderForm('/meals/meal-pancakes/edit', {
      'GET /api/meals/meal-pancakes': meal(),
      'PATCH /api/meals/meal-pancakes': meal(),
    });
    const form = await screen.findByTestId(testIds.mealForm);
    expect(within(row('Salz')).getByLabelText('Unit')).toHaveDisplayValue('No unit');

    await user.type(within(row('Salz')).getByLabelText('Amount'), '5');
    expect(within(row('Salz')).getByLabelText('Unit')).toHaveDisplayValue('g');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, 'PATCH /api/meals/meal-pancakes')).toHaveLength(1),
    );
    await expect(bodyOf(fetchMock, 'PATCH /api/meals/meal-pancakes')).resolves.toMatchObject({
      ingredients: [
        { ingredient_id: FLOUR.id, amount: 200, unit: 'g' },
        { ingredient_id: MILK.id, amount: 300, unit: 'ml' },
        { ingredient_id: EGGS.id, amount: 2, unit: 'piece' },
        { ingredient_id: SALT.id, amount: 5, unit: 'g', note: 'to taste' },
      ],
    });
  });

  it('saves nothing when nothing changed', async () => {
    const { fetchMock, user, router } = renderForm('/meals/meal-pancakes/edit', {
      'GET /api/meals/meal-pancakes': meal(),
    });
    const form = await screen.findByTestId(testIds.mealForm);

    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-pancakes'));
    expect(requestsTo(fetchMock, 'PATCH /api/meals/meal-pancakes')).toHaveLength(0);
  });

  it("refuses to edit someone else's meal", async () => {
    renderForm('/meals/meal-pancakes/edit', {
      'GET /api/meals/meal-pancakes': meal({ owner: BEN, is_owner: false }),
    });

    expect(await screen.findByRole('alert')).toHaveTextContent("You're not allowed to do that.");
    expect(screen.queryByTestId(testIds.mealForm)).not.toBeInTheDocument();
  });

  describe('from the meal picker of a list (LIST-03)', () => {
    const LIST = `/api/lists/${LIST_ID}`;

    function renderFromList(routes: Record<string, unknown> = {}, addToList = LIST_ID) {
      return renderForm(`/meals/new?addToList=${encodeURIComponent(addToList)}`, {
        'POST /api/meals': Response.json(bareMeal({ name: 'Suppe' }), { status: 201 }),
        [`POST ${LIST}/meals`]: listDetail(),
        [`GET ${LIST}`]: listDetail(),
        'GET /api/lists': { lists: [], next_cursor: null },
        ...routes,
      });
    }

    it('adds the new meal to the list and goes back there', async () => {
      const { fetchMock, user, router } = renderFromList();
      const form = await screen.findByTestId(testIds.mealForm);
      expect(screen.getByRole('link', { name: 'Back to the list' })).toHaveAttribute(
        'href',
        `/lists/${LIST_ID}`,
      );

      await user.type(within(form).getByLabelText('Name'), 'Suppe');
      await user.click(within(form).getByRole('button', { name: 'Create meal' }));

      await waitFor(() => expect(router.state.location.pathname).toBe(`/lists/${LIST_ID}`));
      await expect(bodyOf(fetchMock, `POST ${LIST}/meals`)).resolves.toEqual({
        meal_id: 'meal-new',
      });
      expect(await screen.findByTestId(testIds.listMeals)).toBeVisible();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('goes back to the list and says so when the meal could not be added', async () => {
      const { user, router } = renderFromList({
        [`POST ${LIST}/meals`]: errorResponse(503, 'common.service_unavailable'),
      });
      const form = await screen.findByTestId(testIds.mealForm);

      await user.type(within(form).getByLabelText('Name'), 'Suppe');
      await user.click(within(form).getByRole('button', { name: 'Create meal' }));

      await waitFor(() => expect(router.state.location.pathname).toBe(`/lists/${LIST_ID}`));
      expect(await screen.findByRole('alert')).toHaveTextContent(
        "The meal is saved, but it couldn't be added to the list: MealMate is unavailable right now. Please try again later.",
      );
    });

    it('ignores a list that is not a list id and saves the meal as usual', async () => {
      const { fetchMock, user, router } = renderFromList({}, '../me/admin');
      const form = await screen.findByTestId(testIds.mealForm);
      expect(screen.getByRole('link', { name: 'All meals' })).toHaveAttribute('href', '/meals');

      await user.type(within(form).getByLabelText('Name'), 'Suppe');
      await user.click(within(form).getByRole('button', { name: 'Create meal' }));

      await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-new'));
      const paths = fetchMock.mock.calls.map(([request]) => new URL(request.url).pathname);
      // The sync module's refresh of the local copy is not about this list.
      const listPaths = paths.filter((path) => path.startsWith('/api/lists/'));
      expect(listPaths.filter((path) => path !== '/api/lists/sync')).toEqual([]);
    });
  });
});
