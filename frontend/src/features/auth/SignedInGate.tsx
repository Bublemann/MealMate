import { Info, LogOut } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useLogout } from './api';
import { useAuth } from './context';

/**
 * Join and reset links sign someone in. While another user is signed in on this device, they
 * have to log out first (on the server too), so that their session and data don't linger.
 * Once nobody was signed in, the form stays: its own sign-in must not hide it again.
 */
export function SignedInGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { status, user } = useAuth();
  const logout = useLogout();
  const [signedOut, setSignedOut] = useState(false);

  if (!signedOut && status !== 'authenticated' && status !== 'loading') setSignedOut(true);
  if (signedOut || status !== 'authenticated' || !user) return children;
  return (
    <>
      <Alert>
        <Info aria-hidden="true" />
        <AlertDescription>{t('auth.link.signedIn', { name: user.display_name })}</AlertDescription>
      </Alert>
      <Button
        variant="outline"
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
        className="self-start"
      >
        <LogOut aria-hidden="true" />
        {t('me.logout')}
      </Button>
      <ErrorAlert error={logout.error} />
    </>
  );
}
