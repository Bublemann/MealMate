import { useId, useMemo, type ReactNode } from 'react';
import type { TestId } from '@/testIds';
import { ScreenHeadingContext } from './screenHeading';

interface ScreenProps {
  title: string;
  testId: TestId;
  /**
   * `pinned` for Lists, Meals and Ingredients: their pinned block shows the headline as its first
   * element, so it stays put with the block (D-44). `tab` for the other tab screens, whose
   * headline only screen readers get. Detail screens show theirs.
   */
  variant?: 'pinned' | 'tab' | 'detail';
  children: ReactNode;
}

/** A top-level screen: one <h1> and its content, labelled for assistive technology. */
export function Screen({ title, testId, variant = 'detail', children }: ScreenProps) {
  const headingId = useId();
  const heading = useMemo(() => ({ id: headingId, title }), [headingId, title]);

  if (variant === 'pinned') {
    return (
      <section aria-labelledby={headingId} data-testid={testId} className="flex flex-col gap-6">
        <ScreenHeadingContext value={heading}>{children}</ScreenHeadingContext>
      </section>
    );
  }

  return (
    <section aria-labelledby={headingId} data-testid={testId} className="flex flex-col gap-6">
      <h1
        id={headingId}
        className={
          variant === 'tab' ? 'sr-only' : 'text-3xl font-bold tracking-tight wrap-anywhere'
        }
      >
        {title}
      </h1>
      {children}
    </section>
  );
}
