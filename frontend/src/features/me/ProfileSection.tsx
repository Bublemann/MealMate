import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useCurrentUser } from '@/features/auth/context';
import { changeLanguage, isLanguage, LANGUAGE_NAMES, LANGUAGES, useLanguage } from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { testIds } from '@/testIds';
import { useUpdateMe } from './api';

/** Display name and language (ACC-13, I18N-01). */
export function ProfileSection() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const language = useLanguage();
  const languageSelectId = useId();
  const nameUpdate = useUpdateMe();
  const languageUpdate = useUpdateMe();
  const [displayName, setDisplayName] = useState(user.display_name);
  const fields = fieldErrorMessages(t, nameUpdate.error);
  const unchanged = displayName.trim() === user.display_name;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    nameUpdate.mutate({ display_name: displayName.trim() });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('me.profile.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <dl className="flex items-baseline justify-between gap-4">
          <dt className="text-muted-foreground">{t('auth.field.username')}</dt>
          <dd className="font-medium break-all">{user.username}</dd>
        </dl>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <FormField
            label={t('auth.field.displayName')}
            hint={t('auth.field.displayNameHint')}
            error={fields.display_name}
          >
            {(control) => (
              <Input
                {...control}
                data-testid={testIds.displayNameInput}
                name="display_name"
                autoComplete="nickname"
                required
                maxLength={40}
                value={displayName}
                onChange={(event) => {
                  nameUpdate.reset();
                  setDisplayName(event.target.value);
                }}
              />
            )}
          </FormField>
          {!fields.display_name && <ErrorAlert error={nameUpdate.error} />}
          <div className="flex items-center gap-3">
            <Button type="submit" size="compact" disabled={unchanged || nameUpdate.isPending}>
              {t('common.save')}
            </Button>
            <p aria-live="polite" className="text-sm text-muted-foreground">
              {nameUpdate.isSuccess && unchanged && t('common.saved')}
            </p>
          </div>
        </form>
        <div className="flex flex-col gap-2">
          <Label htmlFor={languageSelectId}>{t('me.language')}</Label>
          <NativeSelect
            id={languageSelectId}
            data-testid={testIds.languageSelect}
            value={language}
            disabled={languageUpdate.isPending}
            onChange={(event) => {
              const selected = event.target.value;
              if (!isLanguage(selected)) return;
              // Switch at once; the server keeps the choice for every device (I18N-01).
              void changeLanguage(selected);
              languageUpdate.mutate({ language: selected });
            }}
          >
            {LANGUAGES.map((code) => (
              <NativeSelectOption key={code} value={code} lang={code}>
                {LANGUAGE_NAMES[code]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
          <ErrorAlert error={languageUpdate.error} />
        </div>
      </CardContent>
    </Card>
  );
}
