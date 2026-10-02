import { Check } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * A native checkbox (MNT-05: no extra dependency), drawn as a box in the design tokens. A ticked
 * box is filled and shows a check mark, so colour is not the only signal (A11Y-01). It is as
 * large as the text around it; put it in a `<label>` with its text, which is the tap target.
 */
function Checkbox({ className, ...props }: Omit<React.ComponentProps<'input'>, 'type'>) {
  return (
    <span
      data-slot="checkbox"
      className={cn('relative inline-flex size-[1.25em] shrink-0', className)}
    >
      <input
        type="checkbox"
        className="peer size-full cursor-pointer appearance-none rounded-sm border-2 border-input bg-background transition-colors outline-none checked:border-primary checked:bg-primary focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50"
        {...props}
      />
      <Check
        aria-hidden="true"
        strokeWidth={3}
        className="pointer-events-none absolute inset-0 m-auto hidden size-[0.875em] text-primary-foreground peer-checked:block"
      />
    </span>
  );
}

export { Checkbox };
