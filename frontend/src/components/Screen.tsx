import { useId, useMemo, type ReactNode } from 'react';
import type { TestId } from '@/testIds';
import { ScreenHeadingContext } from './screenHeading';

interface ScreenProps {
  title: string;
  testId: TestId;
  /**
   * `pinned` for Lists, Meals and Ingredients: their pinned block shows the headline as its first
   * element, so it stays put with the block (D-44). Otherwise the headline sits above the content
   * and scrolls with it: on the detail screens and the Settings tab.
   */
  variant?: 'pinned' | 'detail';
  children: ReactNode;
}

/** A top-level screen: one <h1> and its content, labelled for assistive technology. */
export function Screen({ title, testId, variant = 'detail', children }: ScreenProps) {
  const headingId = useId();
  const heading = useMemo(() => ({ id: headingId, title }), [headingId, title]);

  return (
    <section aria-labelledby={headingId} data-testid={testId} className="flex flex-col gap-6">
      {variant === 'pinned' ? (
        <ScreenHeadingContext value={heading}>{children}</ScreenHeadingContext>
      ) : (
        <>
          <h1 id={headingId} className="text-3xl font-bold tracking-tight wrap-anywhere">
            {title}
          </h1>
          {children}
        </>
      )}
    </section>
  );
}
