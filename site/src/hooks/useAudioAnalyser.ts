import { useCallback, useRef, useState } from "react";

/**
 * Capture the tab's audio via getDisplayMedia and expose a live AnalyserNode
 * for real FFT visualization. One-click opt-in (user must share the tab and
 * tick "share audio"). Mixcloud's iframe is cross-origin so we can't hit its
 * audio graph directly — this is the one sanctioned browser route.
 *
 * Chrome/Edge fully support this. Firefox is partial — the prompt will open
 * but "share audio" is often unchecked or missing depending on OS.
 */
export type AnalyserHandle = {
  active: boolean;
  error: string | null;
  supported: boolean;
  requestSync: () => Promise<void>;
  stop: () => void;
  getAnalyser: () => AnalyserNode | null;
};

export function useAudioAnalyser(): AnalyserHandle {
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const supported =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getDisplayMedia;

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    contextRef.current?.close().catch(() => {});
    streamRef.current = null;
    analyserRef.current = null;
    contextRef.current = null;
    setActive(false);
  }, []);

  const requestSync = useCallback(async () => {
    if (!supported) {
      setError("browser doesn't support tab-audio capture");
      return;
    }
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        audio: true,
        // video must be requested for the prompt to include audio on most browsers
        video: { width: { ideal: 1 }, height: { ideal: 1 }, frameRate: 1 },
      });
      const audioTracks = stream.getAudioTracks();
      if (audioTracks.length === 0) {
        stream.getTracks().forEach((t) => t.stop());
        setError('no audio on that share — tick "share audio" next time');
        return;
      }
      // Discard the video — we only needed it as a ticket to get the prompt.
      stream.getVideoTracks().forEach((t) => t.stop());

      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.82;
      source.connect(analyser);
      // DO NOT connect analyser to ctx.destination — tab audio is already
      // audible, piping it again would double it.

      contextRef.current = ctx;
      analyserRef.current = analyser;
      streamRef.current = stream;
      setActive(true);

      audioTracks[0].addEventListener("ended", () => {
        setActive(false);
        analyserRef.current = null;
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "sync failed";
      setError(msg);
    }
  }, [supported]);

  return {
    active,
    error,
    supported,
    requestSync,
    stop,
    getAnalyser: () => analyserRef.current,
  };
}
