import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import {
  changeLanguage,
  isLanguage,
  LANGUAGE_NAMES,
  LANGUAGES,
  useLanguage,
  type Language,
} from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { formatDateTime } from '@/i18n/format';
import { testIds } from '@/testIds';
import { useJoin } from './api';
import { AuthScreen } from './AuthScreen';
import { CodeGate } from './CodeGate';
import { useAuth } from './context';
import { clearLinkCode, useLinkCode } from './linkCode';

/** Registration with an invite link (ACC-01, ACC-04..07). */
export function JoinScreen() {
  const { t } = useTranslation();
  const code = useLinkCode('invite');

  return (
    <AuthScreen title={t('auth.join.title')} testId={testIds.screenJoin}>
      <CodeGate kind="invite" code={code}>
        {(info, validCode) => <JoinForm code={validCode} expiresAt={info.expires_at} />}
      </CodeGate>
    </AuthScreen>
  );
}

function JoinForm({ code, expiresAt }: { code: string; expiresAt: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { status } = useAuth();
  const uiLanguage = useLanguage();
  const languageId = useId();
  const join = useJoin();
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [language, setLanguage] = useState<Language>(uiLanguage);
  const fields = fieldErrorMessages(t, join.error);
  const hasFieldErrors = Object.keys(fields).length > 0;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    join.mutate(
      { code, username, display_name: displayName.trim(), password, language },
      {
        onSuccess: () => {
          clearLinkCode();
          void navigate('/lists', { replace: true });
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <p className="text-muted-foreground">
        {t('auth.join.intro', { date: formatDateTime(expiresAt, uiLanguage) })}
      </p>
      <FormField
        label={t('auth.field.username')}
        hint={t('auth.field.usernameHint')}
        error={fields.username}
      >
        {(control) => (
          <Input
            {...control}
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
            maxLength={30}
            value={username}
            // Usernames are lower case (ACC-05); typing "Anna" gives "anna".
            onChange={(event) => setUsername(event.target.value.toLowerCase())}
          />
        )}
      </FormField>
      <FormField
        label={t('auth.field.displayName')}
        hint={t('auth.field.displayNameHint')}
        error={fields.display_name}
      >
        {(control) => (
          <Input
            {...control}
            name="display_name"
            autoComplete="nickname"
            required
            maxLength={40}
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        )}
      </FormField>
      <FormField
        label={t('auth.field.password')}
        hint={t('auth.field.passwordRules')}
        error={fields.password}
      >
        {(control) => (
          <Input
            {...control}
            type="password"
            name="new-password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        )}
      </FormField>
      <div className="flex flex-col gap-2">
        <Label htmlFor={languageId}>{t('me.language')}</Label>
        <NativeSelect
          id={languageId}
          value={language}
          onChange={(event) => {
            const selected = event.target.value;
            if (!isLanguage(selected)) return;
            setLanguage(selected);
            void changeLanguage(selected);
          }}
        >
          {LANGUAGES.map((lang) => (
            <NativeSelectOption key={lang} value={lang} lang={lang}>
              {LANGUAGE_NAMES[lang]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      {/* Field problems show next to their fields; everything else (e.g. a used code) here. */}
      {!hasFieldErrors && <ErrorAlert error={join.error} />}
      <Button type="submit" disabled={join.isPending || status === 'loading'}>
        {t('auth.join.submit')}
      </Button>
    </form>
  );
}
