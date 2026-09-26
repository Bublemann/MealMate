import { describe, expect, it } from 'vitest';
import openapi from '@/api/generated/openapi.json';
import en from './en.json';
import { LANGUAGES } from '.';

// I18N-03 / I18N-06: every language file has the same keys, no empty strings, the same
// {{placeholders}} and <tags> per key, and a translation for every error code the API can send.
const files = import.meta.glob<Record<string, string>>('./*.json', {
  eager: true,
  import: 'default',
});
const catalogs = Object.fromEntries(
  Object.entries(files).map(([path, catalog]) => [path.replace(/^\.\/(.+)\.json$/, '$1'), catalog]),
);
const reference = Object.keys(en).sort();

it('registers every language file and nothing else', () => {
  expect(Object.keys(catalogs).sort()).toEqual([...LANGUAGES].sort());
});

const placeholders = (text: string) =>
  [...text.matchAll(/\{\{\s*([\w.]+)[^}]*\}\}/g)].map((match) => match[1]).sort();
const tags = (text: string) => [...text.matchAll(/<\/?(\w+)\s*\/?>/g)].map((m) => m[0]).sort();

const { ErrorCode, FieldErrorCode } = openapi.components.schemas;

it('finds the error codes in openapi.json', () => {
  expect(ErrorCode.enum).toContain('common.internal');
  expect(FieldErrorCode.enum).toContain('required');
});

describe.each(Object.entries(catalogs))('translations (%s)', (language, catalog) => {
  it('has exactly the same keys as en.json', () => {
    expect(Object.keys(catalog).sort()).toEqual(reference);
  });

  it('has no empty translations', () => {
    const empty = Object.entries(catalog).filter(([, text]) => text.trim() === '');
    expect(empty.map(([key]) => key)).toEqual([]);
  });

  it.each(reference)('uses the same placeholders and tags as en.json in %s', (key) => {
    const text = catalog[key] ?? '';
    const english = en[key as keyof typeof en];
    expect(placeholders(text), `${language}: ${key}`).toEqual(placeholders(english));
    expect(tags(text), `${language}: ${key}`).toEqual(tags(english));
  });

  it('translates every ErrorCode and FieldErrorCode', () => {
    const required = [
      ...ErrorCode.enum.map((code) => `error.${code}`),
      ...FieldErrorCode.enum.map((code) => `error.field.${code}`),
      'error.client.timeout',
      'error.client.network',
    ];
    expect(required.filter((key) => !(key in catalog))).toEqual([]);
  });

  it('has ten reminders', () => {
    const reminders = Object.keys(catalog).filter((key) => key.startsWith('reminder.'));
    expect(reminders).toEqual(Array.from({ length: 10 }, (_, i) => `reminder.${i + 1}`));
  });
});
