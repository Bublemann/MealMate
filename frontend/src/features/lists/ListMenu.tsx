import { Copy, Pencil, RotateCcw, Share, ShoppingCart, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { MoreMenu, MoreMenuItem, MoreMenuSwitch } from '@/components/MoreMenu';
import { useMoreMenuFocus } from '@/components/useMoreMenuFocus';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useCouple } from '@/features/couple/api';
import type { Category } from '@/features/reference/api';
import type { PendingList } from '@/features/sync/applyPending';
import { useConnected } from '@/features/sync/context';
import { useLanguage } from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { userLabel } from '@/i18n/users';
import { canShare, shareText, type ShareResult } from '@/lib/share';
import { testIds } from '@/testIds';
import {
  useCopyList,
  useDeleteList,
  useReopenList,
  useShopAgain,
  useUpdateList,
  type ListDetail,
} from './api';
import { exportText } from './exportText';
import { listDisplayName } from './format';
import type { ListViewState } from './ListScreen';

/** The longest list name the server takes (LIST-02). */
const MAX_NAME_LENGTH = 60;

/** What a menu action leaves to say below the title: the export's outcome, or an error. */
export type ListNotice = { exported: ShareResult } | { error: unknown } | null;

interface ListMenuProps {
  /** The list with the user's waiting changes applied. */
  list: PendingList;
  categories: readonly Category[];
  /** Says below the title what an action came to; `null` clears it when the next one starts. */
  onNotice: (notice: ListNotice) => void;
}

/**
 * The list's ⋯ menu (D-39), with what the user may do with the list as a whole, in this order:
 * - a draft or a list being shopped: "Rename" for editors (LIST-02), or "Copy to my lists" on
 *   someone else's (VIS-03); "Share as text" (EXP-01); the owner's "Shared with <partner>" switch
 *   while in a couple (CPL-02);
 * - a done list: "Copy to my lists" on someone else's, "Shop again", "Reopen" for editors
 *   (SHOP-06), "Share as text";
 * - last, red, the owner's "Delete" in any state (LIST-13).
 *
 * The server says who may do what (`can_edit`, `is_owner`). Export also works offline from the
 * local copy (EXP-03); the rest needs a connection and is disabled without one (SYNC-03).
 */
export function ListMenu({ list, categories, onNotice }: ListMenuProps) {
  const { t } = useTranslation();
  const offline = !useConnected();
  const language = useLanguage();
  const navigate = useNavigate();
  const couple = useCouple();
  const update = useUpdateList(list.id);
  const remove = useDeleteList(list.id);
  const copy = useCopyList(list.id);
  const shopAgain = useShopAgain(list.id);
  const reopen = useReopenList(list.id);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { trigger, focusMenu } = useMoreMenuFocus();
  const name = listDisplayName(list, t, language);
  const done = list.status === 'done';
  const partner = list.is_owner && !done ? couple.data?.partner : undefined;
  // Show the requested state while it is being saved.
  const sharing = update.isPending ? update.variables.shared_with_partner : undefined;
  const shared = typeof sharing === 'boolean' ? sharing : list.shared_with_partner;
  const onError = (error: unknown) => onNotice({ error });

  function onExport() {
    onNotice(null);
    // Built synchronously and shared before any await: the share sheet needs the tap (plan § 8).
    void shareText(exportText(list, { t, language, categories })).then((exported) =>
      onNotice({ exported }),
    );
  }

  /** "Copy to my lists" and "Shop again" open the new draft, saying what was left out. */
  function onCreated({ list: created, left_out }: { list: ListDetail; left_out: number }) {
    const state: ListViewState = { leftOut: left_out };
    void navigate(`/lists/${created.id}`, { state });
  }

  const copyItem = !list.can_edit && (
    <MoreMenuItem
      testId={testIds.copyList}
      icon={<Copy aria-hidden="true" />}
      disabled={copy.isPending || offline}
      onSelect={() => {
        onNotice(null);
        copy.mutate(undefined, { onSuccess: onCreated, onError });
      }}
    >
      {t('lists.detail.copy')}
    </MoreMenuItem>
  );
  const exportItem = (
    <MoreMenuItem
      testId={testIds.exportList}
      icon={<Share aria-hidden="true" />}
      onSelect={onExport}
    >
      {canShare() ? t('lists.detail.export') : t('lists.detail.exportCopy')}
    </MoreMenuItem>
  );

  return (
    <>
      <MoreMenu
        trigger={trigger}
        danger={
          list.is_owner && (
            <MoreMenuItem
              testId={testIds.deleteList}
              icon={<Trash2 aria-hidden="true" />}
              dialog
              disabled={remove.isPending || offline}
              onSelect={() => setDeleting(true)}
            >
              {t('lists.detail.delete')}
            </MoreMenuItem>
          )
        }
      >
        {!done && (
          <>
            {list.can_edit && (
              <MoreMenuItem
                testId={testIds.renameList}
                icon={<Pencil aria-hidden="true" />}
                dialog
                disabled={offline}
                onSelect={() => {
                  onNotice(null);
                  setRenaming(true);
                }}
              >
                {t('lists.detail.rename')}
              </MoreMenuItem>
            )}
            {copyItem}
            {exportItem}
            {partner && (
              // CPL-02: only the owner, and only while in a couple, shares a list.
              <MoreMenuSwitch
                testId={testIds.shareListSwitch}
                checked={shared}
                disabled={update.isPending || offline}
                onCheckedChange={(value) => {
                  onNotice(null);
                  update.mutate({ shared_with_partner: value }, { onError });
                }}
              >
                {t('lists.detail.share', { name: userLabel(t, partner) })}
              </MoreMenuSwitch>
            )}
          </>
        )}
        {done && (
          <>
            {copyItem}
            <MoreMenuItem
              testId={testIds.shopAgain}
              icon={<ShoppingCart aria-hidden="true" />}
              disabled={shopAgain.isPending || offline}
              onSelect={() => {
                onNotice(null);
                shopAgain.mutate(undefined, { onSuccess: onCreated, onError });
              }}
            >
              {t('lists.done.shopAgain')}
            </MoreMenuItem>
            {list.can_edit && (
              <MoreMenuItem
                testId={testIds.reopenList}
                icon={<RotateCcw aria-hidden="true" />}
                // A list finished here reopens once its *Finish* has been sent.
                disabled={reopen.isPending || offline || list.pendingFinish}
                onSelect={() => {
                  onNotice(null);
                  reopen.mutate(undefined, { onError });
                }}
              >
                {t('lists.done.reopen')}
              </MoreMenuItem>
            )}
            {exportItem}
          </>
        )}
      </MoreMenu>
      {renaming && (
        <RenameDialog list={list} onClose={() => setRenaming(false)} onCloseAutoFocus={focusMenu} />
      )}
      {list.is_owner && (
        <ConfirmDialog
          open={deleting}
          onOpenChange={setDeleting}
          onCloseAutoFocus={focusMenu}
          title={t('lists.detail.deleteTitle', { name })}
          description={t('lists.detail.deleteText')}
          confirmLabel={t('lists.detail.deleteConfirm')}
          destructive
          onConfirm={() => {
            onNotice(null);
            remove.mutate(undefined, {
              onSuccess: () => void navigate('/lists', { replace: true }),
              onError,
            });
          }}
        />
      )}
    </>
  );
}

/** Below the list's title: what export did, in a polite live region, and errors of the menu. */
export function ListNotices({ notice }: { notice: ListNotice }) {
  const { t } = useTranslation();
  const exported = notice && 'exported' in notice ? notice.exported : null;

  return (
    <>
      <p aria-live="polite" className="-mt-2 text-sm text-muted-foreground empty:hidden">
        {exported === 'copied' && t('lists.detail.exportCopied')}
        {exported === 'failed' && t('lists.detail.exportFailed')}
      </p>
      <ErrorAlert error={notice && 'error' in notice ? notice.error : null} />
    </>
  );
}

interface RenameDialogProps {
  list: ListDetail;
  onClose: () => void;
  onCloseAutoFocus: (event: Event) => void;
}

/**
 * LIST-02: editors rename the list; an empty name goes back to the translated default. Mounted
 * while open, so each time it starts from the list's name, without the last error.
 */
function RenameDialog({ list, onClose, onCloseAutoFocus }: RenameDialogProps) {
  const { t } = useTranslation();
  const update = useUpdateList(list.id);
  const [name, setName] = useState(list.name ?? '');
  const nameError = fieldErrorMessages(t, update.error).name;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (update.isPending) return;
    update.mutate({ name: name.trim() || null }, { onSuccess: onClose });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent aria-describedby={undefined} onCloseAutoFocus={onCloseAutoFocus}>
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
