import { StudioView } from "./StudioView";
import { MetricsView } from "./components/metrics/MetricsView";

export function App() {
  if (window.location.pathname === "/metrics") {
    return <MetricsView />;
  }
  return <StudioView />;
}

export default App;
