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

/**
 * The compact "− 4 +" of a meal's servings, 1–99 (LIST-04, D-40): horizontal, each button 44 pt
 * (A11Y-01). Only the number shows; screen readers read it as "4 servings", and again when it
 * changes. Used in a meal's row on a list and wherever servings are chosen for one.
 */
export function ServingsStepper({ value, name, onChange, disabled = false }: ServingsStepperProps) {
  const { t } = useTranslation();

  return (
    <div
      role="group"
      aria-label={t('lists.meals.servingsOf', { name })}
      className="flex shrink-0 items-center"
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
      <span aria-live="polite" className="min-w-9 text-center font-medium tabular-nums">
        <span aria-hidden="true">{value}</span>
        <span className="sr-only">{t('lists.meals.servings', { count: value })}</span>
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
