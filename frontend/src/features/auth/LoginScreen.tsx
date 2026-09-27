import { Info } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { testIds } from '@/testIds';
import { useLogin } from './api';
import { AuthScreen } from './AuthScreen';
import { useAuth } from './context';
import type { EndReason } from './session';
import { StartupScreen } from './StatusScreens';

const REASON_KEYS = {
  revoked: 'auth.login.reason.revoked',
  expired: 'auth.login.reason.expired',
  login_required: 'auth.login.reason.loginRequired',
  logged_out: 'auth.login.reason.loggedOut',
} as const satisfies Record<EndReason, string>;

function redirectTarget(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const { from } = state;
    if (typeof from === 'string' && from.startsWith('/') && !from.startsWith('//')) return from;
  }
  return '/lists';
}

export function LoginScreen() {
  const { t } = useTranslation();
  const { status, reason } = useAuth();
  const location = useLocation();
  const login = useLogin();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  if (status === 'loading') return <StartupScreen />;
  if (status === 'authenticated') return <Navigate to={redirectTarget(location.state)} replace />;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ username: username.trim().toLowerCase(), password });
  }

  return (
    <AuthScreen title={t('auth.login.title')} testId={testIds.screenLogin}>
      {reason && (
        <Alert data-testid={testIds.loginReason}>
          <Info aria-hidden="true" />
          <AlertDescription>{t(REASON_KEYS[reason])}</AlertDescription>
        </Alert>
      )}
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <FormField label={t('auth.field.username')}>
          {(control) => (
            <Input
              {...control}
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          )}
        </FormField>
        <FormField label={t('auth.field.password')}>
          {(control) => (
            <Input
              {...control}
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          )}
        </FormField>
        <ErrorAlert error={login.error} />
        <Button type="submit" disabled={login.isPending}>
          {login.isPending ? t('auth.login.submitting') : t('auth.login.submit')}
        </Button>
      </form>
      <p className="text-sm text-muted-foreground">{t('auth.login.noAccount')}</p>
    </AuthScreen>
  );
}
