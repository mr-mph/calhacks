import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConvexProvider, ConvexReactClient } from "convex/react";
import "./index.css";
import App from "./App.tsx";
import { CONVEX_URL, MARKET_URL } from "./config";

// Markets live in their own app; old #/markets links go straight there.
if (window.location.hash === "#/markets") window.location.replace(MARKET_URL);

const convex = new ConvexReactClient(CONVEX_URL);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConvexProvider client={convex}>
      <App />
    </ConvexProvider>
  </StrictMode>,
);
