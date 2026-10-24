import { Timestamp } from 'spacetimedb';

const MICRO = 1_000_000;

const METRIC_UNITS: Record<string, string> = {
  car_count: 'cars',
  crossings_per_hour: 'crossings per hour',
  person_count: 'people',
};

const COMPARATOR_WORDS: Record<string, string> = {
  '>=': 'at least',
  '>': 'more than',
  '<=': 'at most',
  '<': 'fewer than',
};

export function credits(micro: bigint): string {
  return (Number(micro) / MICRO).toFixed(2);
}

export function percent(p: number): string {
  return `${Math.round(p * 100)}%`;
}

export function metricUnit(metric: string): string {
  return METRIC_UNITS[metric] ?? metric.replace(/_/g, ' ');
}

export function thresholdPhrase(comparator: string, threshold: number, metric: string): string {
  return `${COMPARATOR_WORDS[comparator] ?? comparator} ${threshold} ${metricUnit(metric)}`;
}

function clock(date: Date): string {
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function closesText(closeAt: Timestamp, now: Date): string {
  const at = closeAt.toDate();
  const minutes = Math.round((at.getTime() - now.getTime()) / 60_000);
  if (minutes <= 0) return `Closed at ${clock(at)}`;
  if (minutes < 60) return `Closes in ${minutes} min (${clock(at)})`;
  return `Closes at ${clock(at)}`;
}

export function agoText(unixSeconds: number, now: Date): string {
  const seconds = Math.max(0, Math.round(now.getTime() / 1000 - unixSeconds));
  if (seconds < 60) return `${seconds} s ago`;
  return `${Math.round(seconds / 60)} min ago`;
}

export function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return typeof error === 'string' ? error : 'Something went wrong. Try again.';
}
