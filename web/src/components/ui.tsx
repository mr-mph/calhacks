import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-[16px] bg-surface p-4 shadow-soft ${className}`}>{children}</section>;
}

export type Tone = "neutral" | "free" | "warning" | "critical";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  free: "bg-free/15 text-free",
  warning: "bg-warning/15 text-warning",
  critical: "bg-critical/15 text-critical",
};

export function Chip({ tone = "neutral", children, className = "" }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-[8px] px-2 py-1 text-xs font-semibold ${TONES[tone]} ${className}`}>
      {children}
    </span>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
}

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  const look =
    variant === "primary"
      ? "bg-accent text-on-accent hover:opacity-90"
      : "bg-surface-2 text-text hover:bg-hairline";
  return (
    <button
      type="button"
      className={`press inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold disabled:opacity-50 ${look} ${className}`}
      {...props}
    />
  );
}

export function Caption({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-xs text-muted ${className}`}>{children}</span>;
}

interface EmptyProps {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  command?: string;
}

export function EmptyState({ icon, title, children, command }: EmptyProps) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-[16px] bg-surface p-6 shadow-soft">
      <span className="text-muted">{icon}</span>
      <h2 className="text-lg font-semibold">{title}</h2>
      {children && <p className="max-w-[65ch] text-sm text-muted">{children}</p>}
      {command && (
        <code className="block w-full overflow-x-auto rounded-[8px] bg-surface-2 px-3 py-2 font-mono text-xs whitespace-nowrap">
          {command}
        </code>
      )}
    </div>
  );
}

interface StatTileProps {
  label: string;
  children: ReactNode;
  note?: ReactNode;
  className?: string;
}

export function StatTile({ label, children, note, className = "" }: StatTileProps) {
  return (
    <div className={`flex min-w-0 flex-col gap-1 rounded-[16px] bg-surface p-3 shadow-soft ${className}`}>
      <span className="text-xs font-semibold text-muted">{label}</span>
      <span className="nums text-2xl leading-none font-bold">{children}</span>
      {note && <span className="font-mono text-xs text-muted">{note}</span>}
    </div>
  );
}
