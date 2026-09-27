import { Minus, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { MAX_SERVINGS, MIN_SERVINGS } from '@/features/meals/form';

interface ServingsStepperProps {
  value: number;
  /** The meal's name, for the accessible names of the group and the buttons. */
  name: string;
  onChange: (value: number) => void;
  disabled?: boolean;
}

/** − and + around the servings of a meal on a list, 1–99 (LIST-04). */
export function ServingsStepper({ value, name, onChange, disabled = false }: ServingsStepperProps) {
  const { t } = useTranslation();

  return (
    <div
      role="group"
      aria-label={t('lists.meals.servingsOf', { name })}
      className="flex items-center gap-1"
    >
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={t('lists.meals.fewer', { name })}
        disabled={disabled || value <= MIN_SERVINGS}
        onClick={() => onChange(Math.max(MIN_SERVINGS, value - 1))}
      >
        <Minus aria-hidden="true" />
      </Button>
      <span aria-live="polite" className="min-w-24 text-center font-medium tabular-nums">
        {t('lists.meals.servings', { count: value })}
      </span>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={t('lists.meals.more', { name })}
        disabled={disabled || value >= MAX_SERVINGS}
        onClick={() => onChange(Math.min(MAX_SERVINGS, value + 1))}
      >
        <Plus aria-hidden="true" />
      </Button>
    </div>
  );
}
