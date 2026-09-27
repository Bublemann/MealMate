export type ShareResult = 'shared' | 'copied' | 'cancelled' | 'failed';

/**
 * Opens the native share sheet with `text`, or copies it where there is none (EXP-01, ACC-03).
 *
 * Call it **synchronously** from the click handler, with text that is already built: browsers
 * only allow `navigator.share` (and clipboard writes) within the user activation of the tap
 * (plan § 8). That is why invite and reset links are created with one tap and shared with a
 * second one.
 */
export function shareText(text: string): Promise<ShareResult> {
  if (typeof navigator.share !== 'function') return copyText(text);
  let pending: Promise<void>;
  try {
    pending = navigator.share({ text });
  } catch {
    return copyText(text);
  }
  return pending.then(
    (): ShareResult => 'shared',
    (error: unknown) =>
      error instanceof DOMException && error.name === 'AbortError'
        ? 'cancelled'
        : copyText(text),
  );
}

/** Copies `text` to the clipboard; 'failed' where the clipboard API is missing or refused. */
export async function copyText(text: string): Promise<'copied' | 'failed'> {
  try {
    await navigator.clipboard.writeText(text);
    return 'copied';
  } catch {
    return 'failed';
  }
}

export function canShare(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function';
}
