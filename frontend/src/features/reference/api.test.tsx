import { focusManager, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createQueryClient } from '@/app/queryClient';
import { mockApi, requestsTo } from '@/test/api';
import { CATEGORIES, REFERENCE_ROUTES } from '@/test/ingredients';
import { CATEGORIES_KEY, useCategories, useUnits } from './api';

const MINUTE = 60_000;

function setup() {
  const fetchMock = mockApi(REFERENCE_ROUTES);
  const queryClient = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { fetchMock, queryClient, wrapper };
}

function regainFocus() {
  focusManager.setFocused(false);
  focusManager.setFocused(true);
}

afterEach(() => {
  focusManager.setFocused(undefined);
  vi.useRealTimers();
});

describe('reference data', () => {
  it('loads the categories again 5 minutes later when the app regains focus (ADM-01)', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    const { fetchMock, wrapper } = setup();
    const categories = renderHook(() => useCategories(), { wrapper });
    const units = renderHook(() => useUnits(), { wrapper });
    await waitFor(() => expect(categories.result.current.data).toEqual(CATEGORIES));
    await waitFor(() => expect(units.result.current.isSuccess).toBe(true));

    vi.setSystemTime(Date.now() + 4 * MINUTE);
    regainFocus();
    expect(requestsTo(fetchMock, 'GET /api/categories')).toHaveLength(1);

    vi.setSystemTime(Date.now() + 2 * MINUTE);
    regainFocus();
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/categories')).toHaveLength(2));
    // Units never change.
    expect(requestsTo(fetchMock, 'GET /api/units')).toHaveLength(1);
  });

  it('loads categories older than 5 minutes again when a screen mounts', async () => {
    const { fetchMock, queryClient, wrapper } = setup();
    queryClient.setQueryData(CATEGORIES_KEY, CATEGORIES, { updatedAt: Date.now() - 6 * MINUTE });

    renderHook(() => useCategories(), { wrapper });

    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/categories')).toHaveLength(1));
  });
});
