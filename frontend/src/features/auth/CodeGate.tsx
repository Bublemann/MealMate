import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { isApiError } from '@/api/errors';
import type { components } from '@/api/generated/schema';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { useCodeCheck, type CodeKind } from './api';
import { InvalidLink } from './InvalidLink';

type CodeInfo = components['schemas']['CodeInfo'];

interface CodeGateProps {
  kind: CodeKind;
  code: string | null;
  children: (info: CodeInfo, code: string) => ReactNode;
}

/** Checks the link's code (without consuming it) and shows the form only for a valid one. */
export function CodeGate({ kind, code, children }: CodeGateProps) {
  const { t } = useTranslation();
  const check = useCodeCheck(code);

  if (code === null) return <InvalidLink />;
  if (check.isPending) {
    return (
      <p role="status" className="text-muted-foreground">
        {t('auth.link.checking')}
      </p>
    );
  }
  if (check.isError) {
    const invalid =
      isApiError(check.error) &&
      (check.error.code === 'auth.code_invalid' || check.error.status === 404);
    if (invalid) return <InvalidLink />;
    return (
      <>
        <ErrorAlert error={check.error} />
        <Button variant="outline" onClick={() => void check.refetch()} className="self-start">
          {t('common.retry')}
        </Button>
      </>
    );
  }
  // An invite code opened as a reset link (or the other way round) is no use here.
  if (check.data.kind !== kind) return <InvalidLink />;
  return children(check.data, code);
}
