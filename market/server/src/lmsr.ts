// Logarithmic market scoring rule (Hanson). Shares are whole units; each winning share pays 1 credit.
// Money elsewhere is integer micro-credits, so float results are converted once, at the edge, by toMicro.

export const MICRO_PER_CREDIT = 1_000_000n;

export type Side = 'yes' | 'no';

export const MAX_SHARES_PER_TRADE = 1000;

export interface Book {
  qYes: number;
  qNo: number;
  b: number;
}

function logSumExp(x: number, y: number): number {
  const m = Math.max(x, y);
  return m + Math.log(Math.exp(x - m) + Math.exp(y - m));
}

export function costFunction({ qYes, qNo, b }: Book): number {
  return b * logSumExp(qYes / b, qNo / b);
}

export function priceYes({ qYes, qNo, b }: Book): number {
  return 1 / (1 + Math.exp((qNo - qYes) / b));
}

export function afterBuy(book: Book, side: Side, shares: number): Book {
  return side === 'yes'
    ? { ...book, qYes: book.qYes + shares }
    : { ...book, qNo: book.qNo + shares };
}

export function buyCost(book: Book, side: Side, shares: number): number {
  return costFunction(afterBuy(book, side, shares)) - costFunction(book);
}

// Rounds up so the trader, never the market maker, absorbs rounding; this keeps the
// maker's worst-case loss at or below the b*ln2 subsidy.
export function toMicroCeil(credits: number): bigint {
  return BigInt(Math.ceil(credits * Number(MICRO_PER_CREDIT)));
}

export function maxSubsidy(b: number): number {
  return b * Math.LN2;
}
