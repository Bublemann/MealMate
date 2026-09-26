import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';
import i18n from '@/i18n';

// Components use the app-wide client with a relative base URL; Node's Request (used under jsdom)
// cannot resolve relative URLs, so tests give it jsdom's origin. Tests stub `fetch` as needed.
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>();
  return { ...actual, api: actual.createApiClient({ baseUrl: window.location.origin }) };
});

afterEach(async () => {
  cleanup();
  localStorage.clear();
  await i18n.changeLanguage('en');
});
