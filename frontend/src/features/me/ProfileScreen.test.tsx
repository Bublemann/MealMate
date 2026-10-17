import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LANGUAGE_STORAGE_KEY } from '@/i18n';
import { errorResponse, mockApi, requestsTo, TEST_USER } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

/** PATCH /api/me answers with the user updated by the request body. */
function patchMe(request: Request) {
  return request.json().then((body: object) => ({ ...TEST_USER, ...body }));
}

describe('ProfileScreen', () => {
  it('switches the language, remembers it on the device and saves it on the server', async () => {
    const fetchMock = mockApi({ 'PATCH /api/me': patchMe });
    const { user } = renderApp('/me/profile');

    const select = screen.getByRole('combobox', { name: 'Language' });
    expect(select).toBe(screen.getByTestId(testIds.languageSelect));
    expect(select).toHaveValue('en');
    expect(
      within(select)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Deutsch', 'English']);

    await user.selectOptions(select, 'Deutsch');

    expect(await screen.findByRole('heading', { level: 1, name: 'Profil' })).toBeVisible();
    expect(screen.getByTestId(testIds.backLink)).toHaveAccessibleName('Einstellungen');
    expect(screen.getByRole('combobox', { name: 'Sprache' })).toHaveValue('de');
    expect(screen.getByTestId(testIds.tabLists)).toHaveTextContent('Einkaufslisten');
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('de');
    expect(document.documentElement.lang).toBe('de');
    await waitFor(() => expect(requestsTo(fetchMock, 'PATCH /api/me')).toHaveLength(1));
    const [patch] = requestsTo(fetchMock, 'PATCH /api/me');
    await expect(patch?.json()).resolves.toEqual({ language: 'de' });
    expect(patch?.headers.get('Authorization')).toBe('Bearer test-access-token');

    await waitFor(() => expect(screen.getByTestId(testIds.languageSelect)).toBeEnabled());
    await user.selectOptions(screen.getByTestId(testIds.languageSelect), 'English');

    expect(await screen.findByRole('heading', { level: 1, name: 'Profile' })).toBeVisible();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en');
  });

  it('changes the display name and shows field errors', async () => {
    let taken = true;
    const fetchMock = mockApi({
      'PATCH /api/me': (request: Request) =>
        taken
          ? errorResponse(422, 'common.validation', [
              { loc: ['body', 'display_name'], code: 'taken' },
            ])
          : patchMe(request),
    });
    const { user } = renderApp('/me/profile');

    const input = screen.getByTestId(testIds.displayNameInput);
    expect(input).toHaveValue('Anna');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    await user.clear(input);
    await user.type(input, 'Ben');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Already taken')).toBeVisible();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(/Already taken/);

    taken = false;
    await user.clear(input);
    await user.type(input, 'Annie');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Saved.')).toBeVisible();
    expect(input).not.toHaveAttribute('aria-invalid');
    const last = requestsTo(fetchMock, 'PATCH /api/me').at(-1);
    await expect(last?.json()).resolves.toEqual({ display_name: 'Annie' });
  });
});
