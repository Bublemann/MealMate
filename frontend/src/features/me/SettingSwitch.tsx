import { useId } from 'react';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useCurrentUser } from '@/features/auth/context';
import type { TestId } from '@/testIds';
import { useUpdateMe } from './api';

/** The own settings that are switches, saved on the server (VIS-02, LIST-17). */
type SwitchSetting = 'meals_public' | 'lists_public' | 'carry_over_leftovers';

interface SettingSwitchProps {
  field: SwitchSetting;
  label: string;
  hint: string;
  testId: TestId;
}

/** A switch with its label and one-line hint that saves `field` as soon as it is flipped. */
export function SettingSwitch({ field, label, hint, testId }: SettingSwitchProps) {
  const user = useCurrentUser();
  const update = useUpdateMe();
  const id = useId();
  const hintId = `${id}-hint`;
  // Show the requested state while it is being saved.
  const pending = update.isPending ? update.variables[field] : undefined;
  const checked = typeof pending === 'boolean' ? pending : user[field];

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor={id} className="min-h-7">
            {label}
          </Label>
          <p id={hintId} className="text-sm text-muted-foreground">
            {hint}
          </p>
        </div>
        <Switch
          id={id}
          data-testid={testId}
          aria-describedby={hintId}
          checked={checked}
          disabled={update.isPending}
          onCheckedChange={(value) => update.mutate({ [field]: value })}
        />
      </div>
      <ErrorAlert error={update.error} />
    </div>
  );
}
