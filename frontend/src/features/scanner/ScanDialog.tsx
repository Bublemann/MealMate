import { useTranslation } from 'react-i18next';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { IngredientSummary } from '@/features/ingredients/api';
import { testIds } from '@/testIds';
import { ScanFlow } from './ScanFlow';

interface ScanDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the barcode's ingredient; the dialog closes itself. */
  onIngredient: (ingredient: IngredientSummary) => void;
}

/**
 * The scanner in the meal form's ingredient picker (BAR-01, MEAL-03): the form stays as it is
 * and gets the barcode's ingredient as a new row.
 */
export function ScanDialog({ open, onOpenChange, onIngredient }: ScanDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testIds.scanDialog}>
        <DialogHeader>
          <DialogTitle>{t('scanner.title')}</DialogTitle>
          <DialogDescription>{t('scanner.dialogText')}</DialogDescription>
        </DialogHeader>
        {open && (
          <ScanFlow
            onIngredient={(ingredient) => {
              onOpenChange(false);
              onIngredient(ingredient);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
