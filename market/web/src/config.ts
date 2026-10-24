// Build-time target. `pnpm build` and `pnpm dev:cloud` (mode production) use maincloud and the deployed map app;
// `pnpm dev` uses a local server on the same host that served the page, so phones on the LAN reach the laptop, and
// the map app's dev server (web/, port 5173). VITE_* variables override.
const TARGETS = {
  production: {
    uri: 'wss://maincloud.spacetimedb.com',
    database: 'overhead-market',
    mapUrl: 'https://overhead-live.vercel.app/',
  },
  development: {
    uri: `ws://${location.hostname}:3000`,
    database: 'balloon-market',
    mapUrl: `http://${location.hostname}:5173/`,
  },
};

const target = import.meta.env.MODE === 'production' ? TARGETS.production : TARGETS.development;

export const SPACETIME_URI = import.meta.env.VITE_SPACETIME_URI ?? target.uri;
export const SPACETIME_DATABASE = import.meta.env.VITE_SPACETIME_DB ?? target.database;
export const LIVE_URL = import.meta.env.VITE_LIVE_URL ?? `${target.mapUrl}#/live`;
export const ALERTS_URL = import.meta.env.VITE_ALERTS_URL ?? `${target.mapUrl}#/alerts`;
