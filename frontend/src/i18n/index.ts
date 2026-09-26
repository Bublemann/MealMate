import i18n from 'i18next';
import { initReactI18next, useTranslation } from 'react-i18next';
import de from './de.json';
import en from './en.json';

/** Supported UI languages. Adding one: add `<lang>.json`, then register it here (see README). */
export const LANGUAGES = ['de', 'en'] as const;
export type Language = (typeof LANGUAGES)[number];

/** Each language is named in itself, so everybody can find theirs. */
export const LANGUAGE_NAMES: Record<Language, string> = {
  de: 'Deutsch',
  en: 'English',
};

export const LANGUAGE_STORAGE_KEY = 'mm.language';
const DEFAULT_LANGUAGE: Language = 'en';

export function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value);
}

/** The stored choice, else the browser language: German for `de*`, English otherwise (I18N-02). */
export function detectLanguage(): Language {
  return readStoredLanguage() ?? (navigator.language.toLowerCase().startsWith('de') ? 'de' : 'en');
}

/** Switches the UI language and remembers the choice on this device. */
export async function changeLanguage(language: Language): Promise<void> {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Storage can be unavailable (e.g. private browsing); the choice then lasts for this visit.
  }
  await i18n.changeLanguage(language);
}

/** The active UI language; re-renders the component when it changes. */
export function useLanguage(): Language {
  const { i18n: instance } = useTranslation();
  return isLanguage(instance.resolvedLanguage) ? instance.resolvedLanguage : DEFAULT_LANGUAGE;
}

function readStoredLanguage(): Language | null {
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(stored) ? stored : null;
  } catch {
    return null;
  }
}

i18n.on('languageChanged', (language) => {
  document.documentElement.lang = language;
});

void i18n.use(initReactI18next).init({
  resources: {
    de: { translation: de },
    en: { translation: en },
  },
  lng: detectLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: LANGUAGES,
  keySeparator: false,
  nsSeparator: false,
  interpolation: {
    // React already escapes rendered text.
    escapeValue: false,
  },
  initAsync: false,
});

export default i18n;
