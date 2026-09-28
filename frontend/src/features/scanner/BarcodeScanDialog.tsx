import { useTranslation } from 'react-i18next';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { testIds } from '@/testIds';
import { BarcodeScanner } from './BarcodeScanner';

interface BarcodeScanDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the scanned or typed digits; the dialog closes itself. */
  onBarcode: (barcode: string) => void;
}

/**
 * The scanner for the ingredient form's barcode field: it only reads the digits into the field
 * and looks nothing up, because the form already holds the ingredient's values. A lazy-loaded
 * chunk with the decoder, like `/scan` (PERF-03).
 */
export function BarcodeScanDialog({ open, onOpenChange, onBarcode }: BarcodeScanDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testIds.barcodeScanDialog}>
        <DialogHeader>
          <DialogTitle>{t('scanner.title')}</DialogTitle>
          <DialogDescription>{t('scanner.fieldText')}</DialogDescription>
        </DialogHeader>
        {open && (
          <BarcodeScanner
            onBarcode={(barcode) => {
              onOpenChange(false);
              onBarcode(barcode);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
