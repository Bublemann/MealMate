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
 * The plain scanner over the ingredient pop-up (BAR-01): it hands the scanned or typed digits
 * back and looks nothing up; the pop-up does that (BAR-02/03), so the scanner never imports the
 * form. A lazy-loaded chunk with the decoder (PERF-03).
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
