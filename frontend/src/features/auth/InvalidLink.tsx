import { CircleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { buttonVariants } from '@/components/ui/button';
import { testIds } from '@/testIds';

/** The link has no code, or the code is unknown, used, expired or revoked (auth.code_invalid). */
export function InvalidLink() {
  const { t } = useTranslation();

  return (
    <>
      <Alert variant="destructive" data-testid={testIds.linkInvalid}>
        <CircleAlert aria-hidden="true" />
        <AlertTitle>{t('auth.link.invalidTitle')}</AlertTitle>
        <AlertDescription>{t('auth.link.invalidText')}</AlertDescription>
      </Alert>
      <Link to="/login" className={buttonVariants({ variant: 'outline' })}>
        {t('auth.link.toLogin')}
      </Link>
    </>
  );
}
