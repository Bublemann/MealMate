import { Plus, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  text: string;
  actionLabel: string;
  /** The screen's main action; the button stays disabled until the feature exists. */
  onAction?: () => void;
}

/** One friendly sentence and one main action for a screen without content (UI-03). */
export function EmptyState({ icon: Icon, title, text, actionLabel, onAction }: EmptyStateProps) {
  return (
    <Card className="items-center gap-5 px-6 py-10 text-center">
      <span className="flex size-16 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Icon aria-hidden="true" className="size-8" />
      </span>
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="text-muted-foreground">{text}</p>
      </div>
      <Button onClick={onAction} disabled={!onAction}>
        <Plus aria-hidden="true" />
        {actionLabel}
      </Button>
    </Card>
  );
}
