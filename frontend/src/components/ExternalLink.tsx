import type { ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

type ExternalLinkProps = Omit<ComponentProps<'a'>, 'target' | 'rel'>;

/** A link that opens in a new tab without giving the target page access to MealMate. */
export function ExternalLink({ className, children, ...props }: ExternalLinkProps) {
  const { t } = useTranslation();

  return (
    <a
      target="_blank"
      rel="noopener noreferrer"
      className={cn('font-medium text-primary underline underline-offset-4', className)}
      {...props}
    >
      {children}
      <span className="sr-only"> {t('common.opensInNewTab')}</span>
    </a>
  );
}
