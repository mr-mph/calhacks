// Build-time target. `pnpm build` and `pnpm dev:cloud` (mode production) use maincloud; `pnpm dev` uses a local
// server on the same host that served the page, so phones on the LAN reach the laptop. VITE_* variables override.
const TARGETS = {
  production: { uri: 'wss://maincloud.spacetimedb.com', database: 'overhead-market' },
  development: { uri: `ws://${location.hostname}:3000`, database: 'balloon-market' },
};

const target = import.meta.env.MODE === 'production' ? TARGETS.production : TARGETS.development;

export const SPACETIME_URI = import.meta.env.VITE_SPACETIME_URI ?? target.uri;
export const SPACETIME_DATABASE = import.meta.env.VITE_SPACETIME_DB ?? target.database;
