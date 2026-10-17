import { useLayoutEffect, useRef, type ComponentProps, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useKeyboardOpen } from '@/app/viewport';
import { testIds } from '@/testIds';

/**
 * Between the bar and what sits above it; the same 0.5rem as between the bar and the tab bar
 * (its `bottom` class).
 */
const GAP = '0.5rem';

/**
 * A frosted bar floating just above the tab bar (UI-01, D-39) for the one action a screen is
 * opened for ("Einkauf starten", "Einkauf beenden"), as wide as the content column (the main's
 * max-w-2xl less its px-4, in rem like it). It belongs to the screen, not the app shell, and hides
 * whenever the tab bar does for the keyboard.
 *
 * While it shows, it sets `--floating-bar-space` on <html> to the room it takes (tokens.css), so
 * the content's end scrolls clear of it and the update prompt sits above it (`Layout`).
 */
export function FloatingBar({ children }: { children: ReactNode }) {
  const keyboardOpen = useKeyboardOpen();
  const bar = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = bar.current;
    if (!element) return;
    const root = document.documentElement.style;
    const update = () => {
      const height = element.offsetHeight;
      root.setProperty('--floating-bar-space', height > 0 ? `calc(${height}px + ${GAP})` : '0px');
    };
    update();
    // Its height follows the text size and an error shown in it; hidden, it takes no room.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update);
    observer?.observe(element);
    return () => {
      observer?.disconnect();
      root.removeProperty('--floating-bar-space');
    };
    // Measured again when the keyboard hides or shows it.
  }, [keyboardOpen]);

  return (
    <div
      ref={bar}
      data-testid={testIds.floatingBar}
      hidden={keyboardOpen}
      className="frosted pinned fixed inset-x-4 bottom-[calc(var(--tab-bar-clearance)+0.5rem)] z-10 mx-auto flex max-w-[calc(var(--container-2xl)-2rem)] flex-col gap-[0.5em] rounded-[1em] border border-frosted-border p-[0.5em] shadow-frosted"
    >
      {children}
    </div>
  );
}

/**
 * The bar's full-width button. Like everything in the bar, its text, icon and spacing are in em
 * of the bar's capped text (the `pinned` utility, D-29), so it stops growing with the text size.
 */
export function FloatingBarButton({ className, ...props }: ComponentProps<typeof Button>) {
  return (
    <Button
      className={cn(
        'w-full px-[1em] py-[0.5em] text-[1em] [&_svg:not([class*=size-])]:size-[1.25em]',
        className,
      )}
      {...props}
    />
  );
}
