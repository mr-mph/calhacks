import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConvexProvider, ConvexReactClient } from "convex/react";
import "./index.css";
import App from "./App.tsx";

const url = import.meta.env.VITE_CONVEX_URL as string | undefined;
const root = createRoot(document.getElementById("root")!);

if (url) {
  const convex = new ConvexReactClient(url);
  root.render(
    <StrictMode>
      <ConvexProvider client={convex}>
        <App />
      </ConvexProvider>
    </StrictMode>,
  );
} else {
  root.render(
    <main className="mx-auto flex max-w-xl flex-col gap-3 p-6">
      <h1 className="font-display text-2xl font-bold">Overhead<span className="text-accent">.</span></h1>
      <p className="text-sm text-muted">
        This build has no Convex URL. Run <code className="font-mono">npx convex dev</code> in web/, or set
        VITE_CONVEX_URL before building.
      </p>
    </main>,
  );
}
