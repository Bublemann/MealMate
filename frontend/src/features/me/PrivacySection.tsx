import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useCurrentUser } from '@/features/auth/context';
import { testIds, type TestId } from '@/testIds';
import { useUpdateMe } from './api';

type PrivacyField = 'meals_public' | 'lists_public';

/** The two privacy switches (VIS-02); the partner always sees everything (CPL-04). */
export function PrivacySection() {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('me.privacy.title')}</CardTitle>
        <CardDescription>{t('me.privacy.text')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <PrivacySwitch
          field="meals_public"
          label={t('me.privacy.mealsPublic')}
          hint={t('me.privacy.mealsPublicHint')}
          testId={testIds.mealsPublicSwitch}
        />
        <PrivacySwitch
          field="lists_public"
          label={t('me.privacy.listsPublic')}
          hint={t('me.privacy.listsPublicHint')}
          testId={testIds.listsPublicSwitch}
        />
      </CardContent>
    </Card>
  );
}

interface PrivacySwitchProps {
  field: PrivacyField;
  label: string;
  hint: string;
  testId: TestId;
}

function PrivacySwitch({ field, label, hint, testId }: PrivacySwitchProps) {
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
