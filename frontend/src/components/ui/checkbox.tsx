import { Check } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * A native checkbox (MNT-05: no extra dependency) with its label, which is the tap target of at
 * least 44 pt (A11Y-01) and wraps a long text. The box is drawn in the design tokens; a ticked box
 * is filled and shows a check mark, so colour is not the only signal.
 */
function Checkbox({
  className,
  children,
  ...props
}: Omit<React.ComponentProps<'input'>, 'type'> & { children: React.ReactNode }) {
  return (
    <label
      data-slot="checkbox"
      className={cn(
        'flex min-h-(--tap-target) min-w-0 cursor-pointer items-center gap-3 py-1',
        className,
      )}
    >
      <span className="relative inline-flex size-5 shrink-0">
        <input
          type="checkbox"
          className="peer size-full cursor-pointer appearance-none rounded-sm border-2 border-input bg-background transition-colors outline-none checked:border-primary checked:bg-primary focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
          {...props}
        />
        <Check
          aria-hidden="true"
          strokeWidth={3}
          className="pointer-events-none absolute inset-0 m-auto hidden size-3.5 text-primary-foreground peer-checked:block"
        />
      </span>
      <span className="min-w-0 wrap-break-word">{children}</span>
    </label>
  );
}

export { Checkbox };
