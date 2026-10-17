import { useId, useMemo, type ReactNode } from 'react';
import type { TestId } from '@/testIds';
import { DetailStrip, type BackLink } from './DetailStrip';
import { ScreenHeadingContext } from './screenHeading';

type ScreenProps = {
  title: string;
  testId: TestId;
  /**
   * Where the headline sits. `scrolling` (the default): above the content, scrolling with it, as
   * on the Settings tab and the detail screens. `pinned` for Lists, Meals and Ingredients: their
   * pinned block shows it as its first element, so it stays put with the block (D-44).
   */
  variant?: 'scrolling' | 'pinned';
  children: ReactNode;
} & (
  | {
      /** A detail screen's strip above the title (D-46): its back link "‹ parent"… */
      back: BackLink;
      /** …and the screen's ⋯ button at the strip's right, on screens with actions (D-39). */
      action?: ReactNode;
    }
  | { back?: undefined; action?: undefined }
);

/** A top-level screen: one <h1> and its content, labelled for assistive technology. */
export function Screen({
  title,
  testId,
  variant = 'scrolling',
  back,
  action,
  children,
}: ScreenProps) {
  const headingId = useId();
  const heading = useMemo(() => ({ id: headingId, title }), [headingId, title]);

  return (
    <section aria-labelledby={headingId} data-testid={testId} className="flex flex-col gap-6">
      {variant === 'pinned' ? (
        <ScreenHeadingContext value={heading}>{children}</ScreenHeadingContext>
      ) : (
        <>
          {back && <DetailStrip back={back} action={action} />}
          <h1 id={headingId} className="text-3xl font-bold tracking-tight wrap-anywhere">
            {title}
          </h1>
          {children}
        </>
      )}
    </section>
  );
}
