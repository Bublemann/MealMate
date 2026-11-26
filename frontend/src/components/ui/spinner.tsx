import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';

interface SpinnerProps {
  /** `small` sits inside a button or next to a line of text. */
  size?: 'default' | 'small';
  className?: string;
}

/**
 * The one loading spinner of the app (UI-08). It is decoration only: whoever shows it says what
 * is loading, to screen readers too (`LoadingState`, or the button's own name). Under Reduce
 * Motion it stands still.
 */
export function Spinner({ size = 'default', className }: SpinnerProps) {
  return (
    <LoaderCircle
      aria-hidden="true"
      data-testid={testIds.spinner}
      className={cn(
        'animate-spin text-muted-foreground',
        size === 'small' ? 'size-4 text-current' : 'size-6',
        className,
      )}
    />
  );
}
