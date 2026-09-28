import { CameraOff, Flashlight, FlashlightOff, RefreshCw, Search } from 'lucide-react';
import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { FormField } from '@/components/FormField';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { testIds } from '@/testIds';
import { typedBarcode } from './barcode';
import { decodeVideoFrame, loadDecoder, type DecodedBarcode } from './decoder';

/** A frame is decoded this often; a phone keeps up easily and the battery is spared. */
const FRAME_INTERVAL_MS = 250;
/**
 * Every n-th frame without a result is also searched turned by 90°: in iOS 26 Home Screen apps
 * the camera may deliver frames rotated (O-6, to be confirmed on a real iPhone).
 */
const ROTATE_EVERY = 4;

/** `ended`: the camera went away while in use (unplugged, taken by another app, revoked). */
type CameraProblem = 'denied' | 'unavailable' | 'failed' | 'ended';
type Camera = { stream: MediaStream } | { problem: CameraProblem } | null;

interface BarcodeScannerProps {
  /** Called once with the digits of a scanned or typed barcode. */
  onBarcode: (barcode: string) => void;
  /** Diagnostics only (M1, removed in M9): a camera scan with its format and orientation. */
  onDecoded?: (decoded: DecodedBarcode) => void;
  /** Diagnostics only (M1, removed in M9): the camera's video track once the preview runs. */
  onVideoTrack?: (track: MediaStreamTrack) => void;
}

/**
 * The camera scanner with a manual input that always works (BAR-01). Without a camera, or when
 * access is denied, only the input is shown. The camera stops while the page is hidden and when
 * the scanner is closed; if it goes away while in use, decoding stops and it can be retried.
 * The decoder (a wasm download) is loaded only once there is a camera image to decode.
 */
export function BarcodeScanner({ onBarcode, onDecoded, onVideoTrack }: BarcodeScannerProps) {
  const { t } = useTranslation();
  const visible = usePageVisible();
  const [decoderFailed, setDecoderFailed] = useState(false);
  const { camera, retry } = useCamera(visible && !decoderFailed && cameraSupported());
  const stream = camera && 'stream' in camera ? camera.stream : null;
  const problem: CameraProblem | null = !cameraSupported()
    ? 'unavailable'
    : decoderFailed
      ? 'failed'
      : camera && 'problem' in camera
        ? camera.problem
        : null;

  useEffect(() => {
    if (stream) loadDecoder().catch(() => setDecoderFailed(true));
  }, [stream]);

  return (
    <div className="flex flex-col gap-5">
      {problem ? (
        <Alert data-testid={testIds.scannerCameraMessage}>
          <CameraOff aria-hidden="true" />
          <AlertDescription className="flex flex-col items-start gap-3">
            {t(`scanner.camera.${problem === 'ended' ? 'unavailable' : problem}`)}
            {problem === 'ended' && (
              <Button
                type="button"
                variant="outline"
                size="compact"
                data-testid={testIds.scannerCameraRetry}
                onClick={retry}
              >
                <RefreshCw aria-hidden="true" />
                {t('common.retry')}
              </Button>
            )}
          </AlertDescription>
        </Alert>
      ) : stream ? (
        <CameraPreview
          key={stream.id}
          stream={stream}
          onBarcode={onBarcode}
          onDecoded={onDecoded}
          onVideoTrack={onVideoTrack}
        />
      ) : (
        <CameraPlaceholder />
      )}
      <ManualBarcodeForm onBarcode={onBarcode} />
    </div>
  );
}

function cameraSupported(): boolean {
  return typeof navigator.mediaDevices?.getUserMedia === 'function';
}

function subscribeVisibility(onChange: () => void) {
  document.addEventListener('visibilitychange', onChange);
  return () => document.removeEventListener('visibilitychange', onChange);
}

function usePageVisible(): boolean {
  return useSyncExternalStore(subscribeVisibility, () => document.visibilityState === 'visible');
}

function stopStream(stream: MediaStream) {
  for (const track of stream.getTracks()) track.stop();
}

function problemOf(error: unknown): CameraProblem {
  const name = error instanceof DOMException || error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'denied';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'unavailable';
  return 'failed';
}

/**
 * The back camera's stream while `enabled`; null while it starts or when switched off. When its
 * video ends (the camera went away), the problem `ended`; `retry` starts the camera again.
 */
function useCamera(enabled: boolean): { camera: Camera; retry: () => void } {
  const [camera, setCamera] = useState<Camera>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let stream: MediaStream | null = null;
    function onEnded() {
      if (!active || !stream) return;
      stopStream(stream);
      setCamera({ problem: 'ended' });
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .then((started) => {
        if (!active) {
          stopStream(started);
          return;
        }
        stream = started;
        for (const track of started.getVideoTracks()) track.addEventListener('ended', onEnded);
        setCamera({ stream: started });
      })
      .catch((error: unknown) => {
        if (active) setCamera({ problem: problemOf(error) });
      });
    return () => {
      active = false;
      if (stream) {
        for (const track of stream.getVideoTracks()) track.removeEventListener('ended', onEnded);
        stopStream(stream);
      }
      setCamera(null);
    };
  }, [enabled, attempt]);

  return { camera, retry: () => setAttempt((count) => count + 1) };
}

function CameraPlaceholder() {
  const { t } = useTranslation();

  return (
    <div className="flex aspect-[4/3] w-full items-center justify-center rounded-xl bg-muted p-4 text-center text-muted-foreground">
      <p aria-live="polite">{t('scanner.camera.starting')}</p>
    </div>
  );
}

/** Whether the camera has a light that can be switched on (image capture: `torch`). */
function hasTorch(track: MediaStreamTrack | undefined): boolean {
  // Not every browser has getCapabilities (Firefox before 132).
  // The DOM typings don't know `torch` yet.
  const capabilities = track?.getCapabilities?.();
  return capabilities !== undefined && 'torch' in capabilities && capabilities.torch === true;
}

/** The live camera image, decoded every FRAME_INTERVAL_MS until a barcode is found. */
function CameraPreview({
  stream,
  onBarcode,
  onDecoded,
  onVideoTrack,
}: Pick<BarcodeScannerProps, 'onBarcode' | 'onDecoded' | 'onVideoTrack'> & {
  stream: MediaStream;
}) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const handlers = useRef({ onBarcode, onDecoded });
  const [torchOn, setTorchOn] = useState(false);
  const track = stream.getVideoTracks()[0];

  useEffect(() => {
    handlers.current = { onBarcode, onDecoded };
  });

  useEffect(() => {
    if (track) onVideoTrack?.(track);
  }, [track, onVideoTrack]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream;
    // Autoplay of a muted inline video is allowed; a refusal only leaves the preview still.
    video.play().catch(() => undefined);
  }, [stream]);

  useEffect(() => {
    const canvas = document.createElement('canvas');
    let stopped = false;
    let misses = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      const video = videoRef.current;
      if (stopped || !video) return;
      let barcode: DecodedBarcode | null = null;
      try {
        const rotate = misses % ROTATE_EVERY === ROTATE_EVERY - 1;
        barcode = await decodeVideoFrame(video, canvas, { rotate });
      } catch {
        // A frame that can't be read is skipped; the manual input stays available.
      }
      if (stopped) return;
      if (barcode) {
        stopped = true;
        handlers.current.onDecoded?.(barcode);
        handlers.current.onBarcode(barcode.text);
        return;
      }
      misses += 1;
      timer = setTimeout(() => void tick(), FRAME_INTERVAL_MS);
    }

    timer = setTimeout(() => void tick(), FRAME_INTERVAL_MS);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);

  function toggleTorch() {
    if (!track) return;
    const next = !torchOn;
    const torch: MediaTrackConstraintSet & { torch: boolean } = { torch: next };
    track
      .applyConstraints({ advanced: [torch] })
      .then(() => setTorchOn(next))
      .catch(() => undefined);
  }

  return (
    <div className="relative overflow-hidden rounded-xl bg-black">
      <video
        ref={videoRef}
        data-testid={testIds.scannerVideo}
        aria-label={t('scanner.camera.label')}
        autoPlay
        muted
        playsInline
        className="aspect-[4/3] w-full object-cover"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-[10%] top-1/2 h-1/3 -translate-y-1/2 rounded-lg border-2 border-white/80"
      />
      <p className="absolute inset-x-0 bottom-0 bg-black/60 px-3 py-2 text-center text-sm text-white">
        {t('scanner.camera.hint')}
      </p>
      {hasTorch(track) && (
        <Button
          type="button"
          variant="outline"
          size="icon"
          data-testid={testIds.scannerTorch}
          aria-label={t('scanner.torch')}
          aria-pressed={torchOn}
          onClick={toggleTorch}
          className="absolute top-2 right-2"
        >
          {torchOn ? <FlashlightOff aria-hidden="true" /> : <Flashlight aria-hidden="true" />}
        </Button>
      )}
    </div>
  );
}

type BarcodeHandler = (barcode: string) => void;

function ManualBarcodeForm({ onBarcode }: { onBarcode: BarcodeHandler }) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [invalid, setInvalid] = useState(false);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const barcode = typedBarcode(text);
    setInvalid(barcode === null);
    if (barcode !== null) onBarcode(barcode);
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
      <FormField
        label={t('scanner.manual.label')}
        hint={t('scanner.manual.hint')}
        error={invalid ? t('scanner.manual.invalid') : undefined}
      >
        {(control) => (
          <Input
            {...control}
            name="barcode"
            data-testid={testIds.barcodeInput}
            inputMode="numeric"
            enterKeyHint="search"
            autoComplete="off"
            maxLength={20}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        )}
      </FormField>
      <Button
        type="submit"
        variant="outline"
        data-testid={testIds.barcodeLookup}
        className="self-start"
      >
        <Search aria-hidden="true" />
        {t('scanner.manual.submit')}
      </Button>
    </form>
  );
}
