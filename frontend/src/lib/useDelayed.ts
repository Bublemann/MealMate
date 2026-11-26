import { useEffect, useState } from 'react';

/** How long a load may take before its spinner shows: shorter loads show nothing (UI-08). */
export const LOADING_DELAY_MS = 300;

/** Whether `active` has been true for 300 ms without a break; false again as soon as it isn't. */
export function useDelayed(active: boolean): boolean {
  const [elapsed, setElapsed] = useState(false);

  useEffect(() => {
    if (!active) return;
    const timer = setTimeout(() => setElapsed(true), LOADING_DELAY_MS);
    return () => {
      clearTimeout(timer);
      setElapsed(false);
    };
  }, [active]);

  return active && elapsed;
}
