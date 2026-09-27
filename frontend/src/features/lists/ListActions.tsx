import { Copy, Pencil, Share, Trash2 } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useCouple } from '@/features/couple/api';
import { useLanguage } from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { userLabel } from '@/i18n/users';
import { canShare, shareText, type ShareResult } from '@/lib/share';
import { testIds } from '@/testIds';
import { useCopyList, useDeleteList, useUpdateList, type ListDetail } from './api';
import { exportText } from './exportText';
import { listDisplayName } from './format';
import type { ListViewState } from './ListScreen';

/** The longest list name the server takes (LIST-02). */
const MAX_NAME_LENGTH = 60;

interface ListActionsProps {
  list: ListDetail;
  categoryKeys: ReadonlyMap<string, string>;
}

/**
 * What can be done with the list as a whole: export (everyone, EXP-01), rename (editors,
 * LIST-02), delete and the share switch (owner, LIST-13, CPL-02), or, on someone else's list,
 * "Copy to my lists" (VIS-03). The server says who may do what (`can_edit`, `is_owner`); a done
 * list can't be renamed or shared differently any more (LIST-10).
 */
export function ListActions({ list, categoryKeys }: ListActionsProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const navigate = useNavigate();
  const remove = useDeleteList(list.id);
  const copy = useCopyList(list.id);
  const [exported, setExported] = useState<ShareResult | null>(null);
  const name = listDisplayName(list, t, language);

  function onExport() {
    setExported(null);
    // Built synchronously and shared before any await: the share sheet needs the tap (plan § 8).
    void shareText(exportText(list, { t, language, categoryKeys })).then(setExported);
  }

  function onCopy() {
    copy.mutate(undefined, {
      onSuccess: ({ list: created, left_out }) => {
        const state: ListViewState = { leftOut: left_out };
        void navigate(`/lists/${created.id}`, { state });
      },
    });
  }

  return (
    <div className="-mt-2 flex flex-col gap-3">
      {!list.can_edit && (
        <Card data-testid={testIds.listReadOnly} className="gap-3 px-5 py-4">
          <p>{t('lists.detail.readOnly', { name: userLabel(t, list.owner) })}</p>
          <Button
            data-testid={testIds.copyList}
            disabled={copy.isPending}
            onClick={onCopy}
            className="self-start"
          >
            <Copy aria-hidden="true" />
            {t('lists.detail.copy')}
          </Button>
        </Card>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" data-testid={testIds.exportList} onClick={onExport}>
          <Share aria-hidden="true" />
          {canShare() ? t('lists.detail.export') : t('lists.detail.exportCopy')}
        </Button>
        {list.can_edit && list.status !== 'done' && <RenameDialog list={list} />}
        {list.is_owner && (
          <ConfirmDialog
            trigger={
              <Button
                variant="outline"
                data-testid={testIds.deleteList}
                aria-label={t('lists.detail.deleteLabel', { name })}
                disabled={remove.isPending}
              >
                <Trash2 aria-hidden="true" />
                {t('lists.detail.delete')}
              </Button>
            }
            title={t('lists.detail.deleteTitle', { name })}
            description={t('lists.detail.deleteText')}
            confirmLabel={t('lists.detail.deleteConfirm')}
            destructive
            onConfirm={() =>
              remove.mutate(undefined, {
                onSuccess: () => void navigate('/lists', { replace: true }),
              })
            }
          />
        )}
      </div>
      <p aria-live="polite" className="text-sm text-muted-foreground empty:hidden">
        {exported === 'copied' && t('lists.detail.exportCopied')}
        {exported === 'failed' && t('lists.detail.exportFailed')}
      </p>
      {list.is_owner && list.status !== 'done' && <ShareSwitch list={list} />}
      <ErrorAlert error={remove.error ?? copy.error} />
    </div>
  );
}

/** CPL-02: only the owner, and only while in a couple, shares a list with the partner. */
function ShareSwitch({ list }: { list: ListDetail }) {
  const { t } = useTranslation();
  const couple = useCouple();
  const update = useUpdateList(list.id);
  const id = useId();
  const hintId = `${id}-hint`;
  const partner = couple.data?.partner;
  if (!partner) return null;

  const partnerName = userLabel(t, partner);
  // Show the requested state while it is being saved.
  const pending = update.isPending ? update.variables.shared_with_partner : undefined;
  const checked = typeof pending === 'boolean' ? pending : list.shared_with_partner;

  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor={id} className="min-h-7">
            {t('lists.detail.share', { name: partnerName })}
          </Label>
          <p id={hintId} className="text-sm text-muted-foreground">
            {t('lists.detail.shareHint', { name: partnerName })}
          </p>
        </div>
        <Switch
          id={id}
          data-testid={testIds.shareListSwitch}
          aria-describedby={hintId}
          checked={checked}
          disabled={update.isPending}
          onCheckedChange={(value) => update.mutate({ shared_with_partner: value })}
        />
      </div>
      <ErrorAlert error={update.error} />
    </div>
  );
}

/** LIST-02: editors rename the list; an empty name goes back to the translated default. */
function RenameDialog({ list }: { list: ListDetail }) {
  const { t } = useTranslation();
  const update = useUpdateList(list.id);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(list.name ?? '');
  const nameError = fieldErrorMessages(t, update.error).name;

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      setName(list.name ?? '');
      update.reset();
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (update.isPending) return;
    update.mutate({ name: name.trim() || null }, { onSuccess: () => setOpen(false) });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" data-testid={testIds.renameList}>
          <Pencil aria-hidden="true" />
          {t('lists.detail.rename')}
        </Button>
      </DialogTrigger>
      <DialogContent aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t('lists.detail.renameTitle')}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={onSubmit}
          noValidate
          aria-label={t('lists.detail.renameTitle')}
          className="flex flex-col gap-4"
        >
          <FormField
            label={t('lists.detail.name')}
            hint={t('lists.detail.nameHint', { name: t('lists.defaultName') })}
            error={nameError}
          >
            {(control) => (
              <Input
                {...control}
                name="name"
                autoComplete="off"
                maxLength={MAX_NAME_LENGTH}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            )}
          </FormField>
          <ErrorAlert error={nameError ? null : update.error} />
          <DialogFooter>
            <Button type="submit" disabled={update.isPending}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
