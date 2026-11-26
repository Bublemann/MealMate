import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { testIds } from '@/testIds';
import { Button } from './button';

describe('Button while pending (UI-08)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('ignores further presses at once and shows the small spinner after about 300 ms', () => {
    const onClick = vi.fn();
    const { rerender } = render(
      <Button pending onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole('button', { name: 'Save' });

    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(screen.queryByTestId(testIds.spinner)).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByTestId(testIds.spinner)).toBeVisible();
    // The label stays its name; the spinner is decoration.
    expect(screen.getByRole('button', { name: 'Save' })).toBe(button);

    rerender(
      <Button pending={false} onClick={onClick}>
        Save
      </Button>,
    );
    expect(screen.queryByTestId(testIds.spinner)).not.toBeInTheDocument();
    expect(button).toBeEnabled();
    expect(button).not.toHaveAttribute('aria-busy');
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('shows no spinner for a save that answers within 300 ms', () => {
    const { rerender } = render(<Button pending>Save</Button>);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    rerender(<Button pending={false}>Save</Button>);
    rerender(<Button pending>Save</Button>);
    act(() => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.queryByTestId(testIds.spinner)).not.toBeInTheDocument();
  });
});
