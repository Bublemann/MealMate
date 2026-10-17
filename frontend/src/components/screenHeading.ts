import { createContext, useContext } from 'react';

/** The headline of a `<Screen variant="pinned">`, which its pinned block shows (D-44). */
export interface ScreenHeading {
  /** The heading's id, by which the screen's section is labelled. */
  id: string;
  title: string;
}

export const ScreenHeadingContext = createContext<ScreenHeading | null>(null);

export function useScreenHeading(): ScreenHeading {
  const heading = useContext(ScreenHeadingContext);
  if (!heading) throw new Error('PinnedBlock needs a <Screen variant="pinned">');
  return heading;
}
