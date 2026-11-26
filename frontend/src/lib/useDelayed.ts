import { useEffect, useState } from 'react';

/** How long a load may take before its spinner shows: shorter loads show nothing (UI-08). */
export const LOADING_DELAY_MS = 300;

/** Whether `active` has been true for `ms` (300) without a break; false again as soon as it isn't. */
export function useDelayed(active: boolean, ms = LOADING_DELAY_MS): boolean {
  const [elapsed, setElapsed] = useState(false);

  useEffect(() => {
    if (!active) return;
    const timer = setTimeout(() => setElapsed(true), ms);
    return () => {
      clearTimeout(timer);
      setElapsed(false);
    };
  }, [active, ms]);

  return active && elapsed;
}
