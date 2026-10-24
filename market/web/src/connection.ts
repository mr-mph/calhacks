import { SPACETIME_DATABASE, SPACETIME_URI } from './config';
import { DbConnection } from './module_bindings';

// Each server issues its own tokens, so keep one per database.
const TOKEN_KEY = `overhead-token-${SPACETIME_DATABASE}`;

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
    .withUri(SPACETIME_URI)
    .withDatabaseName(SPACETIME_DATABASE)
    .withToken(readToken())
    .withAutomaticReconnect()
    .onConnect((conn, _identity, token) => {
      saveToken(token);
      conn
        .subscriptionBuilder()
        .onApplied(() => hooks.onReady())
        .onError(() => hooks.onLinkChange('down'))
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
