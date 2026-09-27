import { describe, expect, it } from 'vitest';
import { ApiError } from '@/api/errors';
import i18n from '.';
import { errorMessage } from './errors';

describe('errorMessage', () => {
  const t = i18n.t.bind(i18n);

  it('translates API and client error codes', () => {
    expect(errorMessage(t, new ApiError({ status: 404, code: 'common.not_found' }))).toBe(
      "This doesn't exist (any more).",
    );
    expect(errorMessage(t, new ApiError({ status: 0, code: 'client.network' }))).toBe(
      "Can't reach MealMate. Are you online?",
    );
  });

  it('uses the generic message for unknown codes and non-API errors', () => {
    const generic = 'Something went wrong. Please try again.';
    const unknown = ApiError.fromResponse(409, { code: 'meal.from_the_future' });

    expect(errorMessage(t, unknown)).toBe(generic);
    expect(errorMessage(t, new Error('boom'))).toBe(generic);
  });
});
