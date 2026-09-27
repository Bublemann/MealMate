import { Plus, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import type { TestId } from '@/testIds';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  text: string;
  actionLabel: string;
  /** The action's icon (default: a plus). */
  actionIcon?: LucideIcon;
  /** The screen's main action; the button stays disabled until the feature exists. */
  onAction?: () => void;
  /** The action's test ID, when it is the same action as a button shown with content. */
  actionTestId?: TestId;
}

/** One friendly sentence and one main action for a screen without content (UI-03). */
export function EmptyState({
  icon: Icon,
  title,
  text,
  actionLabel,
  actionIcon: ActionIcon = Plus,
  onAction,
  actionTestId,
}: EmptyStateProps) {
  return (
    <Card className="items-center gap-5 px-6 py-10 text-center">
      <span className="flex size-16 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Icon aria-hidden="true" className="size-8" />
      </span>
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="text-muted-foreground">{text}</p>
      </div>
      <Button data-testid={actionTestId} onClick={onAction} disabled={!onAction}>
        <ActionIcon aria-hidden="true" />
        {actionLabel}
      </Button>
    </Card>
  );
}
