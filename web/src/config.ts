// Build-time target. `pnpm build` (mode production) uses Convex prod and the deployed market page; `pnpm dev` uses
// the Convex dev deployment and the market page's dev server (market/web, port 5174). VITE_* variables override.
const TARGETS = {
  production: {
    convexUrl: "https://agreeable-penguin-576.convex.cloud",
    marketUrl: "https://overhead-market.vercel.app/",
  },
  development: {
    convexUrl: "https://notable-emu-727.convex.cloud",
    marketUrl: `http://${location.hostname}:5174/`,
  },
};

const target = import.meta.env.MODE === "production" ? TARGETS.production : TARGETS.development;

export const CONVEX_URL: string = import.meta.env.VITE_CONVEX_URL ?? target.convexUrl;
export const MARKET_URL: string = import.meta.env.VITE_MARKET_URL ?? target.marketUrl;

// Balloon Patrol files confirmed alerts in this Jira site (atlassian/README.md).
export const JIRA_BROWSE_URL = "https://one-atlas-dqcx.atlassian.net/browse/";
