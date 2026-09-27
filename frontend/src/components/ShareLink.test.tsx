import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { testIds } from '@/testIds';
import { ShareLink } from './ShareLink';

const URL = 'https://mealmate.example/join#code';
const MESSAGE = `1. Tailscale\n2. ${URL}`;

function stubNavigator(name: 'share' | 'clipboard', value: unknown) {
  Object.defineProperty(navigator, name, { value, configurable: true });
}

function renderShareLink() {
  return render(<ShareLink label="Invite link" url={URL} message={MESSAGE} />);
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'share');
  Reflect.deleteProperty(navigator, 'clipboard');
});

describe('ShareLink', () => {
  it('shows the created link in a read-only field', () => {
    renderShareLink();

    const field = screen.getByLabelText('Invite link');
    expect(field).toBe(screen.getByTestId(testIds.shareLinkUrl));
    expect(field).toHaveValue(URL);
    expect(field).toHaveAttribute('readonly');
  });

  it('opens the share sheet synchronously within the tap (ACC-03)', async () => {
    const share = vi.fn(() => Promise.resolve());
    stubNavigator('share', share);
    renderShareLink();

    const button = screen.getByRole('button', { name: 'Share' });
    expect(button).toBe(screen.getByTestId(testIds.shareButton));
    fireEvent.click(button);

    // Called before the click handler returned, i.e. with the user activation still valid.
    expect(share).toHaveBeenCalledExactlyOnceWith({ text: MESSAGE });
    await act(() => Promise.resolve());
    expect(screen.queryByText(/Copied/)).not.toBeInTheDocument();
  });

  it('does nothing more when the user closes the share sheet', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubNavigator(
      'share',
      vi.fn(() => Promise.reject(new DOMException('cancel', 'AbortError'))),
    );
    stubNavigator('clipboard', { writeText });
    renderShareLink();

    fireEvent.click(screen.getByRole('button', { name: 'Share' }));
    await act(() => Promise.resolve());

    expect(writeText).not.toHaveBeenCalled();
  });

  it('copies the message where there is no share sheet', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubNavigator('clipboard', { writeText });
    renderShareLink();

    expect(screen.queryByRole('button', { name: 'Share' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith(MESSAGE);
    expect(await screen.findByText('Copied – paste it into a message.')).toBeVisible();
  });

  it('falls back to copying when sharing fails', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubNavigator(
      'share',
      vi.fn(() => Promise.reject(new DOMException('no', 'NotAllowedError'))),
    );
    stubNavigator('clipboard', { writeText });
    renderShareLink();

    fireEvent.click(screen.getByRole('button', { name: 'Share' }));

    expect(await screen.findByText('Copied – paste it into a message.')).toBeVisible();
    expect(writeText).toHaveBeenCalledWith(MESSAGE);
  });

  it('asks to copy by hand when the clipboard is unavailable', async () => {
    renderShareLink();

    fireEvent.click(screen.getByRole('button', { name: 'Copy message' }));

    expect(
      await screen.findByText("Couldn't copy. Tap the link field and copy it yourself."),
    ).toBeVisible();
  });
});
