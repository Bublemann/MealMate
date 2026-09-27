import { Copy, Share } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { canShare, shareText, type ShareResult } from '@/lib/share';
import { testIds } from '@/testIds';

interface ShareLinkProps {
  /** Label of the link field, e.g. "Invite link". */
  label: string;
  url: string;
  /** The prepared message (in the admin's language) that contains the link. */
  message: string;
}

/**
 * A created invite or reset link with a separate Share button (ACC-03): the link already exists,
 * so the tap opens the share sheet right away. Without a share sheet the button copies instead.
 */
export function ShareLink({ label, url, message }: ShareLinkProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const [result, setResult] = useState<ShareResult | null>(null);
  const sheet = canShare();

  function onShare() {
    setResult(null);
    // No await before this call: the share sheet needs the tap's user activation.
    void shareText(message).then(setResult);
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={inputId}>{label}</Label>
      <Input
        id={inputId}
        data-testid={testIds.shareLinkUrl}
        value={url}
        readOnly
        onFocus={(event) => event.currentTarget.select()}
      />
      <Button data-testid={testIds.shareButton} onClick={onShare} className="self-start">
        {sheet ? <Share aria-hidden="true" /> : <Copy aria-hidden="true" />}
        {sheet ? t('share.share') : t('share.copy')}
      </Button>
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {result === 'copied' && t('share.copied')}
        {result === 'failed' && t('share.failed')}
      </p>
    </div>
  );
}
