import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { testIds } from '@/testIds';
import { BarcodeScanner } from './BarcodeScanner';
import { decodeVideoFrame, loadDecoder } from './decoder';

// jsdom has neither a camera nor a canvas: the camera is a fake stream and the decoder is
// mocked here (decoder.test.ts decodes real images).
vi.mock('./decoder', () => ({ loadDecoder: vi.fn(), decodeVideoFrame: vi.fn() }));

const EAN13 = { text: '4006381333931', format: 'EAN13', orientation: 0 };

function fakeCamera({ torch = false, id = 'stream-1' } = {}) {
  // An EventTarget, so that the track can end ("ended") like a real one.
  const track = Object.assign(new EventTarget(), {
    stop: vi.fn(),
    getCapabilities: vi.fn(() => (torch ? { torch: true } : {})),
    applyConstraints: vi.fn(() => Promise.resolve()),
  });
  const stream = { id, getTracks: () => [track], getVideoTracks: () => [track] };
  return { stream: stream as unknown as MediaStream, track };
}

function stubGetUserMedia(getUserMedia: () => Promise<MediaStream>) {
  const mock = vi.fn(getUserMedia);
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: mock },
    configurable: true,
  });
  return mock;
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true });
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

function renderScanner() {
  const onBarcode = vi.fn();
  const user = userEvent.setup();
  const view = render(<BarcodeScanner onBarcode={onBarcode} />);
  return { ...view, onBarcode, user };
}

beforeEach(() => {
  vi.mocked(loadDecoder).mockReset().mockResolvedValue(undefined);
  vi.mocked(decodeVideoFrame).mockReset().mockResolvedValue(null);
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
});

afterEach(() => {
  Reflect.deleteProperty(navigator, 'mediaDevices');
  Reflect.deleteProperty(document, 'visibilityState');
});

describe('BarcodeScanner', () => {
  it('opens the back camera, loads the decoder and reports the first barcode found', async () => {
    const { stream, track } = fakeCamera();
    const getUserMedia = stubGetUserMedia(() => Promise.resolve(stream));
    vi.mocked(decodeVideoFrame).mockResolvedValueOnce(null).mockResolvedValue(EAN13);
    const { onBarcode, unmount } = renderScanner();

    expect(await screen.findByTestId(testIds.scannerVideo)).toHaveAccessibleName('Camera image');
    expect(getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: 'environment' },
      audio: false,
    });
    // The decoder loads in the effect that follows the stream, not synchronously with it.
    await waitFor(() => expect(loadDecoder).toHaveBeenCalled());
    await waitFor(() => expect(onBarcode).toHaveBeenCalledWith('4006381333931'));
    expect(onBarcode).toHaveBeenCalledTimes(1);
    // Nothing else decoded once the barcode is found.
    const decoded = vi.mocked(decodeVideoFrame).mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(decodeVideoFrame).toHaveBeenCalledTimes(decoded);

    expect(track.stop).not.toHaveBeenCalled();
    unmount();
    expect(track.stop).toHaveBeenCalled();
  });

  it('hands the diagnostics screen the video track and the decoded format', async () => {
    const { stream, track } = fakeCamera();
    stubGetUserMedia(() => Promise.resolve(stream));
    vi.mocked(decodeVideoFrame).mockResolvedValue({ ...EAN13, orientation: 90 });
    const onBarcode = vi.fn();
    const onDecoded = vi.fn();
    const onVideoTrack = vi.fn();
    render(
      <BarcodeScanner onBarcode={onBarcode} onDecoded={onDecoded} onVideoTrack={onVideoTrack} />,
    );

    await waitFor(() => expect(onBarcode).toHaveBeenCalledWith('4006381333931'));
    expect(onDecoded).toHaveBeenCalledWith({ ...EAN13, orientation: 90 });
    expect(onVideoTrack).toHaveBeenCalledWith(track);
  });

  it('also looks for the barcode turned by 90° every fourth frame without a result (O-6)', async () => {
    stubGetUserMedia(() => Promise.resolve(fakeCamera().stream));
    const { onBarcode } = renderScanner();

    await waitFor(() => expect(decodeVideoFrame).toHaveBeenCalledTimes(5), { timeout: 3000 });
    const rotations = vi.mocked(decodeVideoFrame).mock.calls.map(([, , options]) => options);
    expect(rotations).toEqual([
      { rotate: false },
      { rotate: false },
      { rotate: false },
      { rotate: true },
      { rotate: false },
    ]);
    expect(onBarcode).not.toHaveBeenCalled();
  });

  it('offers the light only when the camera has one, and switches it', async () => {
    const { stream, track } = fakeCamera({ torch: true });
    stubGetUserMedia(() => Promise.resolve(stream));
    const { user } = renderScanner();

    const torch = await screen.findByRole('button', { name: 'Light' });
    expect(torch).toHaveAttribute('aria-pressed', 'false');
    await user.click(torch);
    expect(track.applyConstraints).toHaveBeenCalledWith({ advanced: [{ torch: true }] });
    await waitFor(() => expect(torch).toHaveAttribute('aria-pressed', 'true'));
    await user.click(torch);
    expect(track.applyConstraints).toHaveBeenLastCalledWith({ advanced: [{ torch: false }] });
  });

  it('shows no light button for a camera without one', async () => {
    stubGetUserMedia(() => Promise.resolve(fakeCamera().stream));
    renderScanner();

    await screen.findByTestId(testIds.scannerVideo);
    expect(screen.queryByTestId(testIds.scannerTorch)).not.toBeInTheDocument();
  });

  it('stops the camera while the app is in the background and starts it again after', async () => {
    const first = fakeCamera();
    const second = fakeCamera();
    const getUserMedia = stubGetUserMedia(() => Promise.resolve(first.stream));
    renderScanner();
    await screen.findByTestId(testIds.scannerVideo);

    setVisibility('hidden');
    expect(first.track.stop).toHaveBeenCalled();
    expect(screen.queryByTestId(testIds.scannerVideo)).not.toBeInTheDocument();

    getUserMedia.mockImplementation(() => Promise.resolve(second.stream));
    setVisibility('visible');
    await screen.findByTestId(testIds.scannerVideo);
    expect(getUserMedia).toHaveBeenCalledTimes(2);
  });

  it('explains a denied camera and keeps the manual input', async () => {
    stubGetUserMedia(() => Promise.reject(new DOMException('denied', 'NotAllowedError')));
    renderScanner();

    expect(await screen.findByTestId(testIds.scannerCameraMessage)).toHaveTextContent(
      'MealMate may not use the camera',
    );
    expect(screen.queryByTestId(testIds.scannerVideo)).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Barcode' })).toBeVisible();
  });

  it('shows only the manual input without a camera', () => {
    renderScanner();

    expect(screen.getByTestId(testIds.scannerCameraMessage)).toHaveTextContent(
      'No camera available',
    );
    expect(screen.getByRole('textbox', { name: 'Barcode' })).toHaveAttribute(
      'inputmode',
      'numeric',
    );
    expect(screen.queryByTestId(testIds.scannerCameraRetry)).not.toBeInTheDocument();
  });

  it('loads the decoder only once there is a camera image to decode', async () => {
    renderScanner();
    expect(loadDecoder).not.toHaveBeenCalled();

    stubGetUserMedia(() => Promise.reject(new DOMException('denied', 'NotAllowedError')));
    renderScanner();
    await screen.findByText(/MealMate may not use the camera/);
    expect(loadDecoder).not.toHaveBeenCalled();

    let start: (stream: MediaStream) => void = () => undefined;
    const getUserMedia = stubGetUserMedia(() => new Promise((resolve) => (start = resolve)));
    renderScanner();
    await waitFor(() => expect(getUserMedia).toHaveBeenCalled());
    expect(loadDecoder).not.toHaveBeenCalled();
    act(() => start(fakeCamera().stream));
    await waitFor(() => expect(loadDecoder).toHaveBeenCalledTimes(1));
  });

  it('stops decoding when the camera goes away, keeps the input and can start it again', async () => {
    const first = fakeCamera();
    const second = fakeCamera({ id: 'stream-2' });
    const getUserMedia = stubGetUserMedia(() => Promise.resolve(first.stream));
    const { onBarcode, user } = renderScanner();
    await screen.findByTestId(testIds.scannerVideo);
    await waitFor(() => expect(decodeVideoFrame).toHaveBeenCalled());

    act(() => {
      first.track.dispatchEvent(new Event('ended'));
    });

    expect(screen.getByTestId(testIds.scannerCameraMessage)).toHaveTextContent(
      'No camera available',
    );
    expect(screen.queryByTestId(testIds.scannerVideo)).not.toBeInTheDocument();
    expect(first.track.stop).toHaveBeenCalled();
    const decoded = vi.mocked(decodeVideoFrame).mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(decodeVideoFrame).toHaveBeenCalledTimes(decoded);
    expect(screen.getByRole('textbox', { name: 'Barcode' })).toBeVisible();

    getUserMedia.mockImplementation(() => Promise.resolve(second.stream));
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await screen.findByTestId(testIds.scannerVideo);
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId(testIds.scannerCameraMessage)).not.toBeInTheDocument();
    vi.mocked(decodeVideoFrame).mockResolvedValue(EAN13);
    await waitFor(() => expect(onBarcode).toHaveBeenCalledWith('4006381333931'));
  });

  it('falls back to the manual input when the decoder cannot load', async () => {
    const { stream, track } = fakeCamera();
    stubGetUserMedia(() => Promise.resolve(stream));
    vi.mocked(loadDecoder).mockRejectedValue(new Error('blocked'));
    renderScanner();

    expect(await screen.findByTestId(testIds.scannerCameraMessage)).toHaveTextContent(
      "The camera scanner couldn't start",
    );
    await waitFor(() => expect(track.stop).toHaveBeenCalled());
  });

  it('takes a typed barcode without spaces and refuses anything that cannot be one', async () => {
    const { onBarcode, user } = renderScanner();
    const input = screen.getByRole('textbox', { name: 'Barcode' });

    await user.type(input, '12345');
    await user.click(screen.getByRole('button', { name: 'Look up' }));
    expect(input).toHaveAccessibleDescription(/A barcode has 8, 12 or 13 digits/);
    expect(onBarcode).not.toHaveBeenCalled();

    await user.clear(input);
    await user.type(input, '4006 3813 33931{Enter}');
    expect(onBarcode).toHaveBeenCalledWith('4006381333931');
    expect(input).not.toHaveAttribute('aria-invalid');
  });
});
