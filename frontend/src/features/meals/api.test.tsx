import { QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { connectAuth, WRITE_TIMEOUT_MS } from '@/api/client';
import { createQueryClient } from '@/app/queryClient';
import { useTags } from '@/features/reference/api';
import { mockApi, nodeFormClasses, requestsTo } from '@/test/api';
import { bareMeal, MEAL_ROUTES } from '@/test/meals';
import {
  PHOTO_UPLOAD_TIMEOUT_MS,
  useCopyMeal,
  useCreateMeal,
  useDeleteMeal,
  useMealTags,
  useUpdateMeal,
  useUploadMealPhoto,
} from './api';

const ROUTES: Record<string, unknown> = {
  ...MEAL_ROUTES,
  'POST /api/meals': () => Response.json(bareMeal(), { status: 201 }),
  'PATCH /api/meals/meal-new': bareMeal(),
  'POST /api/meals/meal-new/copy': () =>
    Response.json(bareMeal({ id: 'meal-copy' }), { status: 201 }),
  'DELETE /api/meals/meal-new': null,
};

function setup() {
  connectAuth(null);
  const fetchMock = mockApi(ROUTES);
  const queryClient = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { fetchMock, wrapper };
}

afterEach(() => {
  vi.useRealTimers();
});

function useCreate() {
  const create = useCreateMeal();
  return () => create.mutateAsync({ name: 'Neu', servings: 1 });
}

function useUpdate() {
  const update = useUpdateMeal('meal-new');
  return () => update.mutateAsync({ name: 'Neu' });
}

function useCopy() {
  const copy = useCopyMeal('meal-new');
  return () => copy.mutateAsync();
}

function useDelete() {
  const remove = useDeleteMeal('meal-new');
  return () => remove.mutateAsync();
}

describe('meal mutations', () => {
  it.each([
    ['creating', useCreate],
    ['editing', useUpdate],
    ['copying', useCopy],
    ['deleting', useDelete],
  ])('load the tags again after %s a meal', async (_, useMutate) => {
    const { fetchMock, wrapper } = setup();
    const { result } = renderHook(
      () => ({ suggestions: useTags(), filter: useMealTags(), mutate: useMutate() }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.suggestions.isSuccess).toBe(true));
    await waitFor(() => expect(result.current.filter.isSuccess).toBe(true));

    await act(() => result.current.mutate());

    // A new tag shows up in the suggestions and the filter; an unused one leaves the filter.
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/tags')).toHaveLength(2));
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/meals/tags')).toHaveLength(2));
  });

  it('gives a photo upload a minute, not the usual 15 seconds', async () => {
    const node = await nodeFormClasses();
    vi.stubGlobal('FormData', node.FormData);
    const { fetchMock, wrapper } = setup();
    const { result } = renderHook(() => useUploadMealPhoto(), { wrapper });
    // A slow connection: nothing comes back until the request is aborted.
    fetchMock.mockImplementation(
      (_request: Request, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('The operation was aborted.', 'AbortError')),
          );
        }),
    );
    vi.useFakeTimers();
    let settled = false;

    const upload = result.current
      .mutateAsync({ mealId: 'meal-new', file: new node.File(['x'], 'p.jpg') })
      .catch((error: unknown) => error)
      .finally(() => (settled = true));
    for (let i = 0; i < 100 && fetchMock.mock.calls.length === 0; i += 1) {
      await vi.advanceTimersByTimeAsync(0);
    }
    expect(fetchMock).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(PHOTO_UPLOAD_TIMEOUT_MS - WRITE_TIMEOUT_MS);

    await expect(upload).resolves.toMatchObject({ code: 'client.timeout' });
  });
});
