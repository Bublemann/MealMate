import { createContext, useContext, type Dispatch, type SetStateAction } from 'react';

/**
 * What a tab keeps while the app is open (UI-01): its search text and its category choices, and
 * later the cuisine and tag choices. The user filter and the state filter are saved on the server
 * instead.
 */
export interface TabMemories {
  /** `categoryIds`: the categories ticked in the filter panel; none shows every category. */
  ingredients: { search: string; categoryIds: string[] };
}

export type TabWithMemory = keyof TabMemories;

export const INITIAL_TAB_MEMORIES: TabMemories = {
  ingredients: { search: '', categoryIds: [] },
};

export const TabMemoryContext = createContext<{
  memories: TabMemories;
  setMemories: Dispatch<SetStateAction<TabMemories>>;
} | null>(null);

/**
 * The tab's memory and a function that changes part of it. Kept in memory only, not in the URL or
 * browser storage, so it is gone when the app closes (or the session ends).
 */
export function useTabMemory<Tab extends TabWithMemory>(
  tab: Tab,
): [TabMemories[Tab], (change: Partial<TabMemories[Tab]>) => void] {
  const context = useContext(TabMemoryContext);
  if (!context) throw new Error('useTabMemory needs a <TabMemoryProvider>');
  const { memories, setMemories } = context;
  const remember = (change: Partial<TabMemories[Tab]>) =>
    setMemories((current) => ({ ...current, [tab]: { ...current[tab], ...change } }));
  return [memories[tab], remember];
}
