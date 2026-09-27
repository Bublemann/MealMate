import { Merge, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import {
  AlertDialog,
  AlertDialogAction,
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
  useDeleteIngredient,
  useMergeIngredient,
  type Ingredient,
  type IngredientSummary,
} from './api';
import { IngredientPicker } from './IngredientPicker';

/** ING-05 (admins): merge a duplicate into another ingredient, or delete an unused one. */
export function IngredientAdminActions({ ingredient }: { ingredient: Ingredient }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const merge = useMergeIngredient(ingredient.id);
  const remove = useDeleteIngredient(ingredient.id);
  const [picking, setPicking] = useState(false);
  const [target, setTarget] = useState<IngredientSummary | null>(null);
  const name = ingredient.name;
  const busy = merge.isPending || remove.isPending;

  function onPick(picked: IngredientSummary) {
    setPicking(false);
    setTarget(picked);
  }

  function onMerge() {
    if (!target) return;
    merge.mutate(target.id, {
      onSuccess: (into) => void navigate(`/ingredients/${into.id}`, { replace: true }),
    });
    setTarget(null);
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
        <ErrorAlert error={merge.error ?? remove.error} />
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
              {t('ingredients.admin.mergeConfirmTitle', { from: name, into: target?.name ?? '' })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('ingredients.admin.mergeConfirmText', { from: name, into: target?.name ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction destructive onClick={onMerge}>
              {t('ingredients.admin.mergeConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
