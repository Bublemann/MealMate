import type { components } from './generated/schema';

export type ErrorCode = components['schemas']['ErrorCode'];
export type FieldErrorCode = components['schemas']['FieldErrorCode'];
export type FieldError = components['schemas']['FieldError'];
export type ErrorParams = components['schemas']['ErrorResponse']['params'];

/** Errors raised by the client itself, before or instead of an HTTP response. */
export type ClientErrorCode = 'client.timeout' | 'client.network';
export type ApiErrorCode = ErrorCode | ClientErrorCode;

const FALLBACK_CODE: ErrorCode = 'common.internal';

interface ApiErrorInit {
  status: number;
  code: ApiErrorCode;
  params?: ErrorParams;
  fields?: FieldError[];
}

/**
 * Every failed API call rejects with an ApiError. `status` is the HTTP status, or 0 when no
 * response arrived (timeout, network failure). `code` is translated as `error.<code>`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly params: ErrorParams;
  readonly fields: FieldError[];

  constructor({ status, code, params = {}, fields = [] }: ApiErrorInit) {
    super(code);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.params = params;
    this.fields = fields;
  }

  /** Builds an ApiError from an error response, reading the ErrorResponse envelope if present. */
  static fromResponse(status: number, body: unknown): ApiError {
    if (!isRecord(body) || typeof body.code !== 'string' || body.code === '') {
      return new ApiError({ status, code: FALLBACK_CODE });
    }
    return new ApiError({
      status,
      // The backend only sends ErrorCode values; unknown codes from a newer backend fall back to
      // the generic message when translated (see errorKey).
      code: body.code as ErrorCode,
      params: parseParams(body.params),
      fields: parseFields(body.fields),
    });
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** The translation key for an error of any kind; non-API errors map to the generic message. */
export function errorKey(error: unknown): `error.${ApiErrorCode}` {
  return `error.${isApiError(error) ? error.code : FALLBACK_CODE}`;
}

/**
 * The rejected request fields by name: `{"loc": ["body", "username"], "code": "taken"}` becomes
 * `{username: "taken"}`. Only the first error per field is kept.
 */
export function fieldErrorCodes(error: unknown): Partial<Record<string, FieldErrorCode>> {
  const codes: Partial<Record<string, FieldErrorCode>> = {};
  if (!isApiError(error)) return codes;
  for (const { loc, code } of error.fields) {
    const name = loc[0] === 'body' ? loc[1] : loc[loc.length - 1];
    if (typeof name === 'string' && !(name in codes)) codes[name] = code;
  }
  return codes;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseParams(value: unknown): ErrorParams {
  if (!isRecord(value)) return {};
  const params: ErrorParams = {};
  for (const [key, param] of Object.entries(value)) {
    if (typeof param === 'string' || typeof param === 'number' || typeof param === 'boolean') {
      params[key] = param;
    }
  }
  return params;
}

function parseFields(value: unknown): FieldError[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((field: unknown): FieldError[] => {
    if (!isRecord(field) || typeof field.code !== 'string' || !Array.isArray(field.loc)) return [];
    const loc = field.loc.filter(
      (part): part is string | number => typeof part === 'string' || typeof part === 'number',
    );
    return [{ loc, code: field.code as FieldErrorCode }];
  });
}
