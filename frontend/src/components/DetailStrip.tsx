import { ChevronLeft } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { testIds } from '@/testIds';

/** Where a detail screen's back link leads, and what it reads: "‹ Alle Listen". */
export interface BackLink {
  /** The screen's fixed parent (D-46), never a step back in the history. */
  to: string;
  /** The parent's name, in full; the strip shortens it with "…" when it doesn't fit. */
  label: string;
}

export interface DetailStripProps {
  back: BackLink;
  /** The screen's one button at the right, its ⋯ menu (D-39); none on screens without actions. */
  action?: ReactNode;
}

/**
 * The top of every detail screen (UI-01, D-46): "‹ parent" on the left and the screen's ⋯ button
 * on the right, on the frosted surface of the tab bar and the pinned block, stuck below the
 * status bar while the content scrolls under it. Its text and controls stop growing at about the
 * first accessibility size like the pinned block's (the `pinned` utility, D-29), so it stays slim
 * and the screen's title follows below it. `Screen` renders it above the title (its `back` prop).
 */
export function DetailStrip({ back, action }: DetailStripProps) {
  return (
    // Spans the content column across the Layout's px-4, so nothing shows beside it.
    <div
      data-testid={testIds.detailStrip}
      className="frosted pinned sticky top-[env(safe-area-inset-top)] z-10 -mx-4 flex items-center justify-between gap-[0.5em] border-b border-frosted-border px-4 py-[0.25em]"
    >
      {/* One line; a long name is cut with "…" on screen and read in full. */}
      <Link
        to={back.to}
        data-testid={testIds.backLink}
        className="-ml-[0.25em] inline-flex min-h-(--tap-target) min-w-0 items-center gap-[0.25em] rounded-md pr-[0.25em] font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring"
      >
        <ChevronLeft aria-hidden="true" className="size-[1.25em] shrink-0" />
        <span className="truncate">{back.label}</span>
      </Link>
      {action && <div className="flex shrink-0">{action}</div>}
    </div>
  );
}
