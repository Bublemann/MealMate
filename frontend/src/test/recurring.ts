import { vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { summary } from './ingredients';

type Schemas = components['schemas'];

/** Klopapier, every ~4 weeks (automatic), last bought on 2 October, due in 5 days. */
export function recurringItem(
  overrides: Partial<Schemas['RecurringItem']> = {},
): Schemas['RecurringItem'] {
  return {
    id: 'rec-klopapier',
    ingredient: summary('Klopapier', 'other', { base_unit: 'piece' }),
    interval: { value: 4, unit: 'week', automatic: true },
    interval_weeks: 4,
    last_purchased_on: '2026-10-02',
    due_on: '2026-10-30',
    days_until_due: 5,
    due: false,
    last_amount: null,
    ...overrides,
  };
}

/** The answer of `GET /api/recurring-items`; the server counts the due items. */
export function recurringList(items: Schemas['RecurringItem'][]): Schemas['RecurringItemList'] {
  return { items, due_count: items.filter(({ due }) => due).length };
}

/** An unread notice that an admin deleted a recurring ingredient (D-51). */
export function deletedNotice(
  name: string,
  brand: string | null = null,
  id = `notice-${name.toLowerCase()}`,
): Schemas['Notice'] {
  return {
    id,
    kind: 'recurring_item.ingredient_deleted',
    params: { name, brand },
    created_at: '2026-10-20T09:00:00Z',
  };
}

/** The answer of `GET /api/me/notices`. */
export function noticeList(notices: Schemas['Notice'][]): Schemas['NoticeList'] {
  return { notices, count: notices.length };
}

/**
 * jsdom has no ResizeObserver, which Radix's switch uses inside a form (the pop-up's "Automatisch
 * anpassen") to size its hidden input. A test that opens the pop-up stubs one that never reports.
 */
export function stubResizeObserver() {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
}
