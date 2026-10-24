import { DbConnection } from './module_bindings';

const TOKEN_KEY = 'balloon-market-token';

// Phones load the page from the laptop's LAN address, so the database defaults to that same host.
const URI = import.meta.env.VITE_SPACETIME_URI ?? `ws://${location.hostname}:3000`;
const DATABASE = import.meta.env.VITE_SPACETIME_DB ?? 'balloon-market';

const TABLES = ['market', 'account', 'position', 'trade', 'latest_observation'];

function readToken(): string | undefined {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

function saveToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private mode: the identity lasts for this tab only.
  }
}

export interface ConnectionHooks {
  onReady: () => void;
  onLinkChange: (state: 'live' | 'down') => void;
}

export function connect(hooks: ConnectionHooks): DbConnection {
  return DbConnection.builder()
    .withUri(URI)
    .withDatabaseName(DATABASE)
    .withToken(readToken())
    .withAutomaticReconnect()
    .onConnect((conn, _identity, token) => {
      saveToken(token);
      conn
        .subscriptionBuilder()
        .onApplied(() => hooks.onReady())
        .subscribe(TABLES.map(t => `SELECT * FROM ${t}`));
      hooks.onLinkChange('live');
    })
    .onAutomaticReconnect((_conn, _identity, token) => {
      saveToken(token);
      hooks.onLinkChange('live');
    })
    .onDisconnect(() => hooks.onLinkChange('down'))
    .onConnectError(() => hooks.onLinkChange('down'))
    .build();
}
