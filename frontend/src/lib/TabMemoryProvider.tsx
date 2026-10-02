import { useMemo, useState, type ReactNode } from 'react';
import { INITIAL_TAB_MEMORIES, TabMemoryContext } from './tabMemory';

/**
 * Holds every tab's memory (`useTabMemory`) for as long as it is mounted: around the signed-in
 * screens, so it lasts until the app closes or the session ends.
 */
export function TabMemoryProvider({ children }: { children: ReactNode }) {
  const [memories, setMemories] = useState(INITIAL_TAB_MEMORIES);
  const value = useMemo(() => ({ memories, setMemories }), [memories]);

  return <TabMemoryContext value={value}>{children}</TabMemoryContext>;
}
