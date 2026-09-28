import { useId, type ReactNode } from 'react';
import type { TestId } from '@/testIds';

interface ScreenProps {
  title: string;
  testId: TestId;
  children: ReactNode;
}

/** A top-level screen: one <h1> and its content, labelled for assistive technology. */
export function Screen({ title, testId, children }: ScreenProps) {
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} data-testid={testId} className="flex flex-col gap-6">
      <h1 id={headingId} className="text-3xl font-bold tracking-tight wrap-anywhere">
        {title}
      </h1>
      {children}
    </section>
  );
}
