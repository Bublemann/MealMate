import { CloudOff } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import type { TestId } from '@/testIds';

interface OfflineNoticeProps {
  /** The translated message. */
  message: string;
  testId: TestId;
}

/** A calm note that something needs a connection (SYNC-03/09): not an error, nothing broke. */
export function OfflineNotice({ message, testId }: OfflineNoticeProps) {
  return (
    <Alert data-testid={testId}>
      <CloudOff aria-hidden="true" />
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
