import { useTranslation } from 'react-i18next';
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
import { unitLabel } from '@/features/reference/labels';
import { testIds } from '@/testIds';
import type { BaseUnit, UnitMismatch } from './api';

interface BaseUnitConfirmDialogProps {
  /** What the base-unit change would leave not fitting; open while there is something. */
  mismatch: UnitMismatch | null;
  /** The ingredient as it is: its name, and the base unit those amounts fit. */
  name: string;
  baseUnit: BaseUnit;
  /** "Change anyway": save the change, accepting it. */
  onConfirm: () => void;
  /** Called whenever the dialog closes, after `onConfirm` too. */
  onClose: () => void;
}

/**
 * ING-02, D-33: before a base-unit change leaves amounts in meals or on drafts not fitting, names
 * where ("Eier wird in 3 Gerichten und auf 1 Entwurf in g verwendet. Diese Mengen passen dann
 * nicht mehr.") and asks "Trotzdem ändern" or "Abbrechen". Nothing is converted either way.
 */
export function BaseUnitConfirmDialog({
  mismatch,
  name,
  baseUnit,
  onConfirm,
  onClose,
}: BaseUnitConfirmDialogProps) {
  const { t } = useTranslation();
  const meals = mismatch?.meals
    ? t('ingredients.unitMismatch.meals', { count: mismatch.meals })
    : null;
  const drafts = mismatch?.lists
    ? t('ingredients.unitMismatch.drafts', { count: mismatch.lists })
    : null;
  const places =
    meals && drafts
      ? t('ingredients.unitMismatch.mealsAndDrafts', { meals, drafts })
      : meals || drafts;

  return (
    <AlertDialog open={mismatch !== null} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent data-testid={testIds.baseUnitConfirm}>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('ingredients.unitMismatch.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('ingredients.unitMismatch.text', {
              name,
              unit: unitLabel(t, baseUnit),
              places: places ?? '',
            })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            {t('ingredients.unitMismatch.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
