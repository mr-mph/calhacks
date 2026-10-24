import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Play, SpeakerHigh, Stop } from "@phosphor-icons/react";
import type { Alert } from "../lib/data";
import { AlertVoiceContext, readStoredReadAloud, storeReadAloud, useAlertVoice, type AlertVoice } from "../lib/voice";
import { Button, Caption } from "./ui";

// A zero-length WAV played inside the switch's tap: it unlocks this audio element for later alerts on iOS Safari.
const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";

type ProviderProps = {
  open: Alert[] | undefined;
  children: ReactNode;
};

function idsOf(alerts: Alert[]): Set<string> {
  return new Set(alerts.map((a) => a._id));
}

export function AlertVoiceProvider({ open, children }: ProviderProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const seenRef = useRef<Set<string> | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [readAloud, setReadAloudState] = useState(readStoredReadAloud);
  const [isBlocked, setBlocked] = useState(false);

  const element = useCallback((): HTMLAudioElement => {
    if (!audioRef.current) {
      const el = new Audio();
      el.addEventListener("ended", () => setPlayingId(null));
      el.addEventListener("error", () => setPlayingId(null));
      audioRef.current = el;
    }
    return audioRef.current;
  }, []);

  const play = useCallback(
    (id: string, url: string) => {
      const el = element();
      el.src = url;
      setPlayingId(id);
      el.play()
        .then(() => setBlocked(false))
        .catch((e: unknown) => {
          setPlayingId((current) => (current === id ? null : current));
          if (e instanceof DOMException && e.name === "NotAllowedError") setBlocked(true);
        });
    },
    [element],
  );

  const stop = useCallback(() => {
    audioRef.current?.pause();
    setPlayingId(null);
  }, []);

  function setReadAloud(on: boolean) {
    storeReadAloud(on);
    setReadAloudState(on);
    setBlocked(false);
    seenRef.current = on ? idsOf(open ?? []) : null;
    if (on && playingId === null) {
      const el = element();
      el.src = SILENT_WAV;
      el.play().catch(() => undefined);
    }
  }

  useEffect(() => {
    if (!open || !readAloud) return;
    const seen = seenRef.current;
    // Turned on in an earlier visit: only alerts that arrive from now on are read, never the backlog.
    if (seen === null) {
      seenRef.current = idsOf(open);
      return;
    }
    const fresh = open.filter((a) => !seen.has(a._id));
    if (fresh.length === 0) return;
    seenRef.current = new Set([...seen, ...idsOf(fresh)]);
    const newest = fresh.find((a) => a.audioUrl);
    if (newest?.audioUrl) play(newest._id, newest.audioUrl);
  }, [open, readAloud, play]);

  const value: AlertVoice = { playingId, play, stop, readAloud, setReadAloud, isBlocked };
  return <AlertVoiceContext.Provider value={value}>{children}</AlertVoiceContext.Provider>;
}

export function ReadAloudSwitch() {
  const { readAloud, setReadAloud, isBlocked } = useAlertVoice();
  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        role="switch"
        aria-checked={readAloud}
        onClick={() => setReadAloud(!readAloud)}
        className="press inline-flex min-h-11 items-center gap-3 self-start rounded-full bg-surface py-2 pr-4 pl-2 text-sm font-semibold shadow-soft"
      >
        <span
          aria-hidden="true"
          className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${readAloud ? "bg-text" : "bg-surface-2"}`}
        >
          <span
            className={`absolute top-1 size-4 rounded-full transition-[left] ${readAloud ? "left-5 bg-bg" : "left-1 bg-muted"}`}
          />
        </span>
        <SpeakerHigh size={16} aria-hidden="true" />
        Read new alerts aloud
      </button>
      {isBlocked ? (
        <p role="status" className="text-sm text-warning">
          This browser blocked sound. Turn the switch off and on again to allow it.
        </p>
      ) : (
        <Caption>Voice by Grok. Plays on this phone only, for alerts that arrive while this page is open.</Caption>
      )}
    </div>
  );
}

export function PlayAlertButton({ alert }: { alert: Alert }) {
  const { playingId, play, stop } = useAlertVoice();
  if (!alert.audioUrl) return null;
  const isPlaying = playingId === alert._id;
  const url = alert.audioUrl;
  return (
    <div className="flex items-center gap-3">
      <Button onClick={() => (isPlaying ? stop() : play(alert._id, url))} aria-pressed={isPlaying}>
        {isPlaying ? <Stop size={16} weight="bold" aria-hidden="true" /> : <Play size={16} weight="bold" aria-hidden="true" />}
        {isPlaying ? "Stop" : "Play alert"}
      </Button>
      <Caption>Voice by Grok</Caption>
    </div>
  );
}
