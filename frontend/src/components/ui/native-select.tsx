import { ChevronDownIcon } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

/** A styled native <select>: the OS picker is the most usable one on the iPhone. */
function NativeSelect({ className, ...props }: React.ComponentProps<'select'>) {
  return (
    <div
      className="group/native-select relative w-full has-[select:disabled]:opacity-50"
      data-slot="native-select-wrapper"
    >
      <select
        data-slot="native-select"
        className={cn(
          'min-h-(--tap-target) w-full min-w-0 appearance-none rounded-md border border-input bg-background py-2 pr-10 pl-3 text-(length:--control-font-size) transition-[color,box-shadow] outline-none disabled:pointer-events-none disabled:cursor-not-allowed',
          'focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring',
          'aria-invalid:border-destructive aria-invalid:ring-destructive/20',
          className,
        )}
        {...props}
      />
      <ChevronDownIcon
        className="pointer-events-none absolute top-1/2 right-3 size-5 -translate-y-1/2 text-muted-foreground select-none"
        aria-hidden="true"
        data-slot="native-select-icon"
      />
    </div>
  );
}

function NativeSelectOption({ className, ...props }: React.ComponentProps<'option'>) {
  return (
    <option
      data-slot="native-select-option"
      className={cn('bg-[Canvas] text-[CanvasText]', className)}
      {...props}
    />
  );
}

export { NativeSelect, NativeSelectOption };
