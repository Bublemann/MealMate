import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { testIds } from '@/testIds';
import { LoadingState } from './LoadingState';

describe('LoadingState (UI-08)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('shows nothing for a quick load and the spinner after about 300 ms', () => {
    render(<LoadingState />);
    const status = screen.getByRole('status');
    expect(status).toBeEmptyDOMElement();

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(status).toBeEmptyDOMElement();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(status).toHaveTextContent('Loading…');
    expect(screen.getByTestId(testIds.spinner)).toBeVisible();
  });

  it('can name what it waits for, shown next to the spinner', () => {
    render(<LoadingState label="Searching Open Food Facts…" />);
    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(screen.getByRole('status')).toHaveTextContent('Searching Open Food Facts…');
    expect(screen.getByText('Searching Open Food Facts…')).toBeVisible();
    expect(screen.getByTestId(testIds.spinner)).toBeVisible();
  });
});
