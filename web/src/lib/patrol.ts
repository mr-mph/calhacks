import { useState } from "react";

const STORAGE_KEY = "overhead-patrol-code";
export const WRONG_PATROL_CODE = "Wrong patrol code";

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(code: string | null): void {
  try {
    if (code) localStorage.setItem(STORAGE_KEY, code);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // private mode: the code lasts until the tab closes
  }
}

export interface PatrolCode {
  code: string | null;
  save: (code: string) => void;
  forget: () => void;
}

export function usePatrolCode(): PatrolCode {
  const [code, setCode] = useState(readStored);
  return {
    code,
    save: (next) => {
      writeStored(next);
      setCode(next);
    },
    forget: () => {
      writeStored(null);
      setCode(null);
    },
  };
}
