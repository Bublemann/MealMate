import { CircleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { errorMessage } from '@/i18n/errors';

/** Shows the translated message of a failed request, or nothing. */
export function ErrorAlert({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;

  return (
    <Alert variant="destructive">
      <CircleAlert aria-hidden="true" />
      <AlertDescription>{errorMessage(t, error)}</AlertDescription>
    </Alert>
  );
}
