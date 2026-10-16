import { screen, within } from '@testing-library/react';
import { expect } from 'vitest';
import { testIds } from '@/testIds';

/**
 * Expects the tab's headline `name` (D-44) to be its one level-1 heading and the first element of
 * the pinned block, so it stays put with the block while the content scrolls (UI-01). Returns it,
 * to check that it is the very same element later.
 */
export function expectPinnedHeadline(name: string): HTMLElement {
  const block = screen.getByTestId(testIds.pinnedBlock);
  const headline = within(block).getByRole('heading', { level: 1, name });
  expect(screen.getAllByRole('heading', { level: 1 })).toEqual([headline]);
  expect(block.firstElementChild).toBe(headline);
  return headline;
}
