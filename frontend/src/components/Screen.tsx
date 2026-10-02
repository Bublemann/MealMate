import { useId, type ReactNode } from 'react';
import type { TestId } from '@/testIds';

interface ScreenProps {
  title: string;
  testId: TestId;
  /**
   * `tab` for the four tab screens (Lists, Meals, Ingredients, Me), whose headline only screen
   * readers get: the tab bar already says where the user is (UI-01). Detail screens show theirs.
   */
  variant?: 'tab' | 'detail';
  children: ReactNode;
}

/** A top-level screen: one <h1> and its content, labelled for assistive technology. */
export function Screen({ title, testId, variant = 'detail', children }: ScreenProps) {
  const headingId = useId();

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
