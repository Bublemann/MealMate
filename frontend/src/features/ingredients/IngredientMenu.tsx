import { CircleAlert, Merge, Pencil, Trash2 } from 'lucide-react';
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
import { useConnected } from '@/features/sync/context';
import { testIds } from '@/testIds';
import {
  unitMismatch,
  useDeleteIngredient,
  useMergeIngredient,
  type Ingredient,
  type IngredientMerge,
  type IngredientSummary,
  type UnitMismatch,
} from './api';
import { IngredientFormDialog } from './IngredientFormDialog';
import { IngredientPicker } from './IngredientPicker';
import { ingredientLabel } from './label';

interface IngredientMenuProps {
  ingredient: Ingredient;
  /** Shows an error of an action below the title; `null` clears it when the next one starts. */
  onError: (error: unknown) => void;
}

/**
 * The ingredient's ⋯ menu (D-39): "Edit" (ING-04), and for admins "Merge…" and, red and last,
 * "Delete" (ING-05). Each needs a connection (SYNC-03). A merge that would leave amounts not
 * fitting the ingredient that stays asks once more, naming how many (D-33).
 */
export function IngredientMenu({ ingredient, onError }: IngredientMenuProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const admin = useCurrentUser().role === 'admin';
  const offline = !useConnected();
  const merge = useMergeIngredient(ingredient.id);
  const remove = useDeleteIngredient(ingredient.id);
  const [editing, setEditing] = useState(false);
  const [picking, setPicking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [target, setTarget] = useState<IngredientSummary | null>(null);
  const { trigger, focusMenu } = useMoreMenuFocus();
  // What the merge into `target` would leave not fitting, once the server said so; kept while
  // the accepting request runs.
  const [mismatch, setMismatch] = useState<UnitMismatch | null>(null);
  const name = ingredientLabel(ingredient.name, ingredient.brand);
  const into = target ? ingredientLabel(target.name, target.brand) : '';
  const busy = merge.isPending || remove.isPending || offline;

  function onPick(picked: IngredientSummary) {
    setPicking(false);
    setMismatch(null);
    setTarget(picked);
  }

  function onMerge() {
    if (!target) return;
    const body: IngredientMerge = { into_id: target.id };
    if (mismatch) body.accept_unit_mismatch = true;
    merge.mutate(body, {
      onSuccess: (kept) => {
        setTarget(null);
        void navigate(`/ingredients/${kept.id}`, { replace: true });
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
              testId={testIds.deleteIngredient}
              icon={<Trash2 aria-hidden="true" />}
              destructive
              dialog
              disabled={busy}
              onSelect={() => setDeleting(true)}
            >
              {t('ingredients.admin.delete')}
            </MoreMenuItem>
          )
        }
      >
        <MoreMenuItem
          testId={testIds.editIngredient}
          icon={<Pencil aria-hidden="true" />}
          dialog
          disabled={offline}
          onSelect={() => setEditing(true)}
        >
          {t('ingredients.detail.edit')}
        </MoreMenuItem>
        {admin && (
          <MoreMenuItem
            testId={testIds.mergeIngredient}
            icon={<Merge aria-hidden="true" />}
            dialog
            disabled={busy}
            onSelect={() => {
              onError(null);
              setPicking(true);
            }}
          >
            {t('ingredients.admin.merge')}
          </MoreMenuItem>
        )}
      </MoreMenu>

      <IngredientFormDialog
        open={editing}
        onOpenChange={setEditing}
        onCloseAutoFocus={focusMenu}
        ingredient={ingredient}
      />

      {admin && (
        <>
          <Dialog open={picking} onOpenChange={setPicking}>
            <DialogContent onCloseAutoFocus={focusMenu}>
              <DialogHeader>
                <DialogTitle>{t('ingredients.admin.mergeTitle', { name })}</DialogTitle>
                <DialogDescription>{t('ingredients.admin.mergeText', { name })}</DialogDescription>
              </DialogHeader>
              <IngredientPicker
                label={t('ingredients.admin.mergePicker')}
                excludeIds={[ingredient.id]}
                allowCreate={false}
                onSelect={onPick}
              />
            </DialogContent>
          </Dialog>

          <AlertDialog open={target !== null} onOpenChange={(open) => !open && setTarget(null)}>
            <AlertDialogContent onCloseAutoFocus={focusMenu}>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t('ingredients.admin.mergeConfirmTitle', { from: name, into })}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t('ingredients.admin.mergeConfirmText', { from: name, into })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              {mismatch && (
                <Alert variant="destructive" data-testid={testIds.mergeUnitMismatch}>
                  <CircleAlert aria-hidden="true" />
                  <AlertDescription>
                    {t('ingredients.admin.mergeUnitMismatch', { count: mismatch.amounts, into })}
                  </AlertDescription>
                </Alert>
              )}
              <AlertDialogFooter>
                <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                <Button variant="destructive" disabled={merge.isPending} onClick={onMerge}>
                  {mismatch
                    ? t('ingredients.admin.mergeAnyway')
                    : t('ingredients.admin.mergeConfirm')}
                </Button>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <ConfirmDialog
            open={deleting}
            onOpenChange={setDeleting}
            onCloseAutoFocus={focusMenu}
            title={t('ingredients.admin.deleteTitle', { name })}
            description={t('ingredients.admin.deleteText')}
            confirmLabel={t('ingredients.admin.deleteConfirm')}
            destructive
            onConfirm={() => {
              onError(null);
              remove.mutate(undefined, {
                onSuccess: () => void navigate('/ingredients', { replace: true }),
                onError,
              });
            }}
          />
        </>
      )}
    </>
  );
}
