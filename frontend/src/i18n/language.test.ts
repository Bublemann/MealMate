import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n, { changeLanguage, detectLanguage, LANGUAGE_STORAGE_KEY } from '.';

describe('detectLanguage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([
    ['de-DE', 'de'],
    ['de-AT', 'de'],
    ['DE', 'de'],
    ['en-US', 'en'],
    ['fr-FR', 'en'],
    ['', 'en'],
  ])('maps the browser language %j to %s', (browserLanguage, expected) => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue(browserLanguage);
    expect(detectLanguage()).toBe(expected);
  });

  it('prefers the stored choice', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-GB');
    localStorage.setItem(LANGUAGE_STORAGE_KEY, 'de');
    expect(detectLanguage()).toBe('de');
  });

  it('ignores an unsupported stored value', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-CH');
    localStorage.setItem(LANGUAGE_STORAGE_KEY, 'xx');
    expect(detectLanguage()).toBe('de');
  });

  it('falls back to the browser language when storage is unavailable', () => {
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-DE');
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    expect(detectLanguage()).toBe('de');
  });
});

describe('changeLanguage', () => {
  it('switches the UI language, stores it and updates <html lang>', async () => {
    await changeLanguage('de');

    expect(i18n.resolvedLanguage).toBe('de');
    expect(i18n.t('nav.lists')).toBe('Listen');
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('de');
    expect(document.documentElement.lang).toBe('de');
  });

  it('still switches when storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });

    await changeLanguage('de');

    expect(i18n.resolvedLanguage).toBe('de');
  });
});
