import { useTranslation } from 'react-i18next';
import { ToggleChip } from '@/components/ui/chip';
import type { UserRef } from '@/features/meals/api';
import { userLabel } from '@/i18n/users';
import type { TestId } from '@/testIds';

interface UserFilterChipsProps {
  users: readonly UserRef[];
  /** Users whose chip is switched off. */
  hidden: readonly string[];
  /** The signed-in user, shown as `meLabel`. */
  meId: string;
  meLabel: string;
  /** Names the chip group, e.g. "Show meals of". */
  label: string;
  testId: TestId;
  /** Called with the hidden users after a chip was switched. */
  onChange: (hidden: string[]) => void;
}

/**
 * One chip per user that switches their meals or lists on or off (MEAL-10, UI-02); a
 * deactivated user is marked as such (ADM-02).
 */
export function UserFilterChips({
  users,
  hidden,
  meId,
  meLabel,
  label,
  testId,
  onChange,
}: UserFilterChipsProps) {
  const { t } = useTranslation();

  function onToggle(userId: string) {
    onChange(hidden.includes(userId) ? hidden.filter((id) => id !== userId) : [...hidden, userId]);
  }

  return (
    <ul data-testid={testId} aria-label={label} className="flex flex-wrap gap-2">
      {users.map((person) => (
        <li key={person.id} className="max-w-full">
          <ToggleChip pressed={!hidden.includes(person.id)} onClick={() => onToggle(person.id)}>
            {person.id === meId ? meLabel : userLabel(t, person)}
          </ToggleChip>
        </li>
      ))}
    </ul>
  );
}
