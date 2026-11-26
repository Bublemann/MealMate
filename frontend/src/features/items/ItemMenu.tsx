import { CircleAlert, Merge, Pencil, Repeat, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { MoreMenu, MoreMenuItem } from '@/components/MoreMenu';
import { useMoreMenuFocus } from '@/components/useMoreMenuFocus';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useCurrentUser } from '@/features/auth/context';
import { itemOf, useRecurringItems } from '@/features/recurring/api';
import { RecurringDialog } from '@/features/recurring/RecurringDialog';
import { useConnected } from '@/features/sync/context';
import { testIds } from '@/testIds';
import {
  unitMismatch,
  useDeleteItem,
  useMergeItem,
  type Item,
  type ItemMerge,
  type ItemSummary,
  type UnitMismatch,
} from './api';
import { ItemFormDialog } from './ItemFormDialog';
import { ItemPicker } from './ItemPicker';
import { itemLabel } from './label';

interface ItemMenuProps {
  item: Item;
  /** Shows an error of an action below the title; `null` clears it when the next one starts. */
  onError: (error: unknown) => void;
}

/**
 * The item's ⋯ menu (D-39): "Edit" (ING-04), "Regelmäßig kaufen…" (LIST-16: the recurring
 * pop-up, for editing when the item is recurring already), and for admins "Merge…" and, red and last,
 * "Delete" (ING-05). Each needs a connection (SYNC-03). A merge that would leave amounts not
 * fitting the item that stays asks once more, naming how many (D-33).
 */
export function ItemMenu({ item, onError }: ItemMenuProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const admin = useCurrentUser().role === 'admin';
  const offline = !useConnected();
  const merge = useMergeItem(item.id);
  const remove = useDeleteItem(item.id);
  const [editing, setEditing] = useState(false);
  const [recurringOpen, setRecurringOpen] = useState(false);
  const recurringItems = useRecurringItems();
  const [picking, setPicking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [target, setTarget] = useState<ItemSummary | null>(null);
  const { trigger, focusMenu } = useMoreMenuFocus();
  // What the merge into `target` would leave not fitting, once the server said so; kept while
  // the accepting request runs.
  const [mismatch, setMismatch] = useState<UnitMismatch | null>(null);
  const name = itemLabel(item.name, item.brand);
  const into = target ? itemLabel(target.name, target.brand) : '';
  const busy = merge.isPending || remove.isPending || offline;

  function onPick(picked: ItemSummary) {
    setPicking(false);
    setMismatch(null);
    setTarget(picked);
  }

  function onMerge() {
    if (!target) return;
    const body: ItemMerge = { into_id: target.id };
    if (mismatch) body.accept_unit_mismatch = true;
    merge.mutate(body, {
      onSuccess: (kept) => {
        setTarget(null);
        void navigate(`/items/${kept.id}`, { replace: true });
      },
      // The confirmation stays open to name what won't fit; other errors show below the title.
      onError: (error) => {
        const counts = unitMismatch(error);
        if (counts) {
          setMismatch(counts);
        } else {
          setTarget(null);
          onError(error);
        }
      },
    });
  }

  return (
    <>
      <MoreMenu
        trigger={trigger}
        danger={
          admin && (
            <MoreMenuItem
              testId={testIds.deleteItem}
              icon={<Trash2 aria-hidden="true" />}
              dialog
              disabled={busy}
              onSelect={() => setDeleting(true)}
            >
              {t('items.admin.delete')}
            </MoreMenuItem>
          )
        }
      >
        <MoreMenuItem
          testId={testIds.editItem}
          icon={<Pencil aria-hidden="true" />}
          dialog
          disabled={offline}
          onSelect={() => setEditing(true)}
        >
          {t('items.detail.edit')}
        </MoreMenuItem>
        <MoreMenuItem
          testId={testIds.buyRegularly}
          icon={<Repeat aria-hidden="true" />}
          dialog
          // Until the set is known (loading, or it failed to load), the pop-up wouldn't know
          // whether to add or edit.
          disabled={offline || !recurringItems.data}
          onSelect={() => {
            onError(null);
            setRecurringOpen(true);
          }}
        >
          {t('recurring.buyRegularly')}
        </MoreMenuItem>
        {admin && (
          <MoreMenuItem
            testId={testIds.mergeItem}
            icon={<Merge aria-hidden="true" />}
            dialog
            disabled={busy}
            onSelect={() => {
              onError(null);
              setPicking(true);
            }}
          >
            {t('items.admin.merge')}
          </MoreMenuItem>
        )}
      </MoreMenu>

      <ItemFormDialog
        open={editing}
        onOpenChange={setEditing}
        onCloseAutoFocus={focusMenu}
        item={item}
      />

      <RecurringDialog
        target={recurringOpen ? { item, recurring: itemOf(recurringItems.data, item.id) } : null}
        onClose={() => setRecurringOpen(false)}
        onCloseAutoFocus={focusMenu}
      />

      {admin && (
        <>
          <Dialog open={picking} onOpenChange={setPicking}>
            <DialogContent onCloseAutoFocus={focusMenu}>
              <DialogHeader>
                <DialogTitle>{t('items.admin.mergeTitle', { name })}</DialogTitle>
                <DialogDescription>{t('items.admin.mergeText', { name })}</DialogDescription>
              </DialogHeader>
              <ItemPicker
                label={t('items.admin.mergePicker')}
                excludeIds={[item.id]}
                allowCreate={false}
                onSelect={onPick}
              />
            </DialogContent>
          </Dialog>

          <AlertDialog open={target !== null} onOpenChange={(open) => !open && setTarget(null)}>
            <AlertDialogContent onCloseAutoFocus={focusMenu}>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t('items.admin.mergeConfirmTitle', { from: name, into })}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t('items.admin.mergeConfirmText', { from: name, into })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              {mismatch && (
                <Alert variant="destructive" data-testid={testIds.mergeUnitMismatch}>
                  <CircleAlert aria-hidden="true" />
                  <AlertDescription>
                    {t('items.admin.mergeUnitMismatch', { count: mismatch.amounts, into })}
                  </AlertDescription>
                </Alert>
              )}
              <AlertDialogFooter>
                <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                <Button variant="destructive" pending={merge.isPending} onClick={onMerge}>
                  {mismatch ? t('items.admin.mergeAnyway') : t('items.admin.mergeConfirm')}
                </Button>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <ConfirmDialog
            open={deleting}
            onOpenChange={setDeleting}
            onCloseAutoFocus={focusMenu}
            title={t('items.admin.deleteTitle', { name })}
            description={t('items.admin.deleteText')}
            confirmLabel={t('items.admin.deleteConfirm')}
            destructive
            onConfirm={() => {
              onError(null);
              remove.mutate(undefined, {
                onSuccess: () => void navigate('/items', { replace: true }),
                onError,
              });
            }}
          />
        </>
      )}
    </>
  );
}
