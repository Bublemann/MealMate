import { useEffect, useState } from 'react';
import type { CodeKind } from './api';

const PENDING_CODE_KEY = 'mm.pendingCode';

interface PendingCode {
  kind: CodeKind;
  code: string;
}

function readPending(kind: CodeKind): string | null {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(PENDING_CODE_KEY) ?? 'null');
    const pending = value as PendingCode | null;
    return pending?.kind === kind && typeof pending.code === 'string' ? pending.code : null;
  } catch {
    return null;
  }
}

function readCode(kind: CodeKind): string | null {
  let fromHash = '';
  try {
    fromHash = decodeURIComponent(window.location.hash.slice(1)).trim();
  } catch {
    // A malformed escape: treat the link as broken.
    return null;
  }
  if (!fromHash) return readPending(kind);
  try {
    // Survives a reload of this tab only; removed once the form succeeds.
    sessionStorage.setItem(PENDING_CODE_KEY, JSON.stringify({ kind, code: fromHash }));
  } catch {
    // Without storage a reload loses the code; the link can simply be opened again.
  }
  return fromHash;
}

/**
 * The code of an invite or reset link (`/join#<code>`, `/reset#<code>`). The fragment never
 * reaches the server (ACC-04); it is removed from the address bar right away so it doesn't stay
 * in the history or get shared by accident.
 */
export function useLinkCode(kind: CodeKind): string | null {
  const [code] = useState(() => readCode(kind));

  useEffect(() => {
    if (!window.location.hash) return;
    const { pathname, search } = window.location;
    window.history.replaceState(window.history.state, '', `${pathname}${search}`);
  }, []);

  return code;
}

/** Forgets the pending code after it has been used. */
export function clearLinkCode(): void {
  try {
    sessionStorage.removeItem(PENDING_CODE_KEY);
  } catch {
    // Nothing stored.
  }
}
