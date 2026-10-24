import { createContext, useContext } from "react";

export const READ_ALOUD_KEY = "overhead-read-aloud";

export interface AlertVoice {
  playingId: string | null;
  play: (id: string, url: string) => void;
  stop: () => void;
  readAloud: boolean;
  setReadAloud: (on: boolean) => void;
  // The browser refused to play without a tap (autoplay policy), so reading aloud needs one more tap on the switch.
  isBlocked: boolean;
}

export const AlertVoiceContext = createContext<AlertVoice | null>(null);

export function useAlertVoice(): AlertVoice {
  const voice = useContext(AlertVoiceContext);
  if (!voice) throw new Error("useAlertVoice needs <AlertVoiceProvider>");
  return voice;
}

export function readStoredReadAloud(): boolean {
  try {
    return localStorage.getItem(READ_ALOUD_KEY) === "on";
  } catch {
    return false;
  }
}

export function storeReadAloud(on: boolean): void {
  try {
    if (on) localStorage.setItem(READ_ALOUD_KEY, "on");
    else localStorage.removeItem(READ_ALOUD_KEY);
  } catch {
    // private mode: the setting lasts until the tab closes
  }
}
