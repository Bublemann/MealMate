import { describe, expect, it } from 'vitest';
import readme from '../README.md?raw';
import { testIds } from './testIds';

const START = '<!-- test-ids:start -->';
const END = '<!-- test-ids:end -->';

function documentedIds(): [string, string][] {
  const section = readme.slice(readme.indexOf(START), readme.indexOf(END));
  return [...section.matchAll(/^\|\s*`(\w+)`\s*\|\s*`([\w-]+)`\s*\|/gm)].map(([, key, id]) => [
    key ?? '',
    id ?? '',
  ]);
}

describe('testIds', () => {
  it('are unique', () => {
    const ids = Object.values(testIds);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('are listed in README.md between the test-ids markers, in order', () => {
    expect(readme).toContain(START);
    expect(readme).toContain(END);
    // On failure, copy the expected rows into the README table.
    expect(documentedIds()).toEqual(Object.entries(testIds));
  });
});
