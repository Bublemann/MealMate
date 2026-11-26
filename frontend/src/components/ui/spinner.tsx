import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';

interface SpinnerProps {
  /** `small` sits inside a button, as large as the button's icons. */
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
        size === 'small' ? 'text-current' : 'size-6',
        className,
      )}
    />
  );
}
