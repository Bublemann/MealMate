import * as SwitchPrimitive from '@radix-ui/react-switch';
import { Check } from 'lucide-react';
import type * as React from 'react';
import { cn } from '@/lib/utils';

// The visible track is 28 px high; the transparent ::before extends the tap target to 48 px
// (A11Y-01). "On" is shown by the thumb position and a check mark, not only by colour.
function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'group/switch peer relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border-2 border-transparent transition-colors outline-none before:absolute before:-inset-x-1 before:-inset-y-2.5 focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none flex size-6 items-center justify-center rounded-full bg-background shadow-sm transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0"
      >
        <Check
          aria-hidden="true"
          className="hidden size-4 text-primary group-data-[state=checked]/switch:block"
        />
      </SwitchPrimitive.Thumb>
    </SwitchPrimitive.Root>
  );
}

export { Switch };
