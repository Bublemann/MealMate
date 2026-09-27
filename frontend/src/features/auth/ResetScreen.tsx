import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useLanguage } from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { formatDateTime } from '@/i18n/format';
import { testIds } from '@/testIds';
import { useResetPassword } from './api';
import { AuthScreen } from './AuthScreen';
import { CodeGate } from './CodeGate';
import { useAuth } from './context';
import { clearLinkCode, useLinkCode } from './linkCode';

/** Setting a new password with a reset link from an admin (ACC-10). */
export function ResetScreen() {
  const { t } = useTranslation();
  const code = useLinkCode('reset');

  return (
    <AuthScreen title={t('auth.reset.title')} testId={testIds.screenReset}>
      <CodeGate kind="reset" code={code}>
        {(info, validCode) => (
          <ResetForm code={validCode} username={info.username ?? ''} expiresAt={info.expires_at} />
        )}
      </CodeGate>
    </AuthScreen>
  );
}

function ResetForm({
  code,
  username,
  expiresAt,
}: {
  code: string;
  username: string;
  expiresAt: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const language = useLanguage();
  const { status } = useAuth();
  const reset = useResetPassword();
  const [password, setPassword] = useState('');
  const fields = fieldErrorMessages(t, reset.error);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    reset.mutate(
      { code, password },
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
        {t('auth.reset.intro', { date: formatDateTime(expiresAt, language) })}
      </p>
      <FormField label={t('auth.field.username')}>
        {(control) => (
          // Read-only, but present so password managers save the new password for this account.
          <Input {...control} name="username" autoComplete="username" value={username} readOnly />
        )}
      </FormField>
      <FormField
        label={t('auth.field.newPassword')}
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
      {!fields.password && <ErrorAlert error={reset.error} />}
      <Button type="submit" disabled={reset.isPending || status === 'loading'}>
        {t('auth.reset.submit')}
      </Button>
    </form>
  );
}
