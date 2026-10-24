import { useSyncExternalStore } from "react";
import { useQuery } from "convex/react";
import { api } from "../convex/_generated/api";
import { AlertVoiceProvider } from "./components/AlertVoice";
import { AlertsView } from "./components/AlertsView";
import { LiveView } from "./components/LiveView";
import { BottomTabs, TopBar, type Tab } from "./components/Nav";

function subscribeHash(cb: () => void): () => void {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
}

function currentTab(): Tab {
  const id = window.location.hash.replace(/^#\/?/, "");
  return id === "alerts" ? id : "live";
}

export default function App() {
  const tab = useSyncExternalStore(subscribeHash, currentTab);
  const alerts = useQuery(api.live.alerts);
  const openAlerts = alerts?.open.length ?? 0;

  return (
    <AlertVoiceProvider open={alerts?.open}>
      <div className="min-h-dvh">
        <TopBar tab={tab} openAlerts={openAlerts} />
        <main className="mx-auto max-w-7xl px-4 pt-4 pb-28 md:pb-12">
          {tab === "live" && <LiveView openAlerts={openAlerts} />}
          {tab === "alerts" && <AlertsView />}
        </main>
        <BottomTabs tab={tab} openAlerts={openAlerts} />
      </div>
    </AlertVoiceProvider>
  );
}
