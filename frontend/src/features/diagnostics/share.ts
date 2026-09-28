import type { ResultLine } from './results';

/**
 * What a `navigator.share` call ended with. iOS rejects with `AbortError` when the user closes
 * the share sheet (so the sheet did open) and with `NotAllowedError` when the tap's user
 * activation has expired (about 5 s, plan § 8): the diagnostics tell the two apart.
 */
export type ShareOutcome =
  | { kind: 'shared' }
  | { kind: 'cancelled' }
  | { kind: 'activationExpired' }
  | { kind: 'unsupported' }
  | { kind: 'error'; name: string };

export function classifyShareError(error: unknown): ShareOutcome {
  const name = error instanceof DOMException || error instanceof Error ? error.name : '';
  if (name === 'AbortError') return { kind: 'cancelled' };
  if (name === 'NotAllowedError') return { kind: 'activationExpired' };
  return { kind: 'error', name: name || String(error) };
}

/**
 * Shares `text` and reports the outcome. `navigator.share` is called before the first `await`,
 * so called from a click handler it runs within the tap's user activation.
 */
export async function tryShare(
  text: string,
  share: Navigator['share'] | undefined = typeof navigator.share === 'function'
    ? navigator.share.bind(navigator)
    : undefined,
): Promise<ShareOutcome> {
  if (!share) return { kind: 'unsupported' };
  try {
    await share({ text });
    return { kind: 'shared' };
  } catch (error) {
    return classifyShareError(error);
  }
}

/** The result line of a share test; `waitedMs` is how long the tap waited before sharing. */
export function shareLine(outcome: ShareOutcome, waitedMs?: number): ResultLine {
  const waited = waitedMs === undefined ? '' : ` (shared ${Math.round(waitedMs)} ms after the tap)`;
  switch (outcome.kind) {
    case 'shared':
      return { status: 'ok', value: `shared${waited}` };
    case 'cancelled':
      return { status: 'ok', value: `AbortError: sheet opened, cancelled by the user${waited}` };
    case 'activationExpired':
      return { status: 'failed', value: `NotAllowedError: user activation expired${waited}` };
    case 'unsupported':
      return { status: 'failed', value: 'navigator.share is missing (the app copies instead)' };
    case 'error':
      return { status: 'failed', value: `${outcome.name}${waited}` };
  }
}
