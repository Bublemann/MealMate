import { CircleAlert, Merge, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { testIds } from '@/testIds';
import {
  unitMismatch,
  useDeleteIngredient,
  useMergeIngredient,
  type Ingredient,
  type IngredientMerge,
  type IngredientSummary,
} from './api';
import { IngredientPicker } from './IngredientPicker';
import { ingredientLabel } from './label';

/**
 * ING-05 (admins): merge a duplicate into another ingredient, or delete an unused one. A merge that
 * would leave amounts not fitting the ingredient that stays asks once more, naming how many (D-33).
 */
export function IngredientAdminActions({ ingredient }: { ingredient: Ingredient }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const merge = useMergeIngredient(ingredient.id);
  const remove = useDeleteIngredient(ingredient.id);
  const [picking, setPicking] = useState(false);
  const [target, setTarget] = useState<IngredientSummary | null>(null);
  const name = ingredientLabel(ingredient.name, ingredient.brand);
  const into = target ? ingredientLabel(target.name, target.brand) : '';
  const busy = merge.isPending || remove.isPending;
  // Shown in the confirmation, which stays open for it.
  const mismatch = unitMismatch(merge.error);

  function onPick(picked: IngredientSummary) {
    setPicking(false);
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
      onError: (error) => {
        if (!unitMismatch(error)) setTarget(null);
      },
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('ingredients.admin.title')}</CardTitle>
        <CardDescription>{t('ingredients.admin.text')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            data-testid={testIds.mergeIngredient}
            disabled={busy}
            onClick={() => {
              merge.reset();
              remove.reset();
              setPicking(true);
            }}
          >
            <Merge aria-hidden="true" />
            {t('ingredients.admin.merge')}
          </Button>
          <ConfirmDialog
            trigger={
              <Button
                variant="destructive"
                data-testid={testIds.deleteIngredient}
                disabled={busy}
                aria-label={t('ingredients.admin.deleteLabel', { name })}
              >
                <Trash2 aria-hidden="true" />
                {t('ingredients.admin.delete')}
              </Button>
            }
            title={t('ingredients.admin.deleteTitle', { name })}
            description={t('ingredients.admin.deleteText')}
            confirmLabel={t('ingredients.admin.deleteConfirm')}
            onConfirm={() => {
              merge.reset();
              remove.mutate(undefined, {
                onSuccess: () => void navigate('/ingredients', { replace: true }),
              });
            }}
            destructive
          />
        </div>
        <ErrorAlert error={(mismatch ? null : merge.error) ?? remove.error} />
      </CardContent>

      <Dialog open={picking} onOpenChange={setPicking}>
        <DialogContent>
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
        <AlertDialogContent>
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
              {mismatch ? t('ingredients.admin.mergeAnyway') : t('ingredients.admin.mergeConfirm')}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
