import { useEffect, useState } from "react";
import { Gauge, FileSpreadsheet } from "lucide-react";
import { getMetrics } from "../../api";
import { getNested } from "../../utils/formatters";
import { SummaryCard } from "../common/SummaryCard";

export function MetricsView() {
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void getMetrics().then(setMetrics);
  }, []);

  return (
    <main className="studio-shell technical">
      <header className="hero-bar">
        <div>
          <p className="eyebrow">Technical model view</p>
          <h1>Metrics</h1>
          <p className="hero-copy">
            Vista separada para evaluar modelo, versiones, baselines y evidencia tecnica sin mezclarlo con el flujo operativo.
          </p>
        </div>
        <Gauge size={34} />
      </header>
      <section className="metrics-layout">
        <SummaryCard
          label="Promoted model"
          value={getNested(metrics, ["promoted_model", "model_name"])}
          detail={getNested(metrics, ["promoted_model", "primary_variant"])}
        />
        <SummaryCard
          label="Scenario variant"
          value={getNested(metrics, ["promoted_model", "scenario_variant"])}
          detail={getNested(metrics, ["promoted_model", "series_policy"])}
        />
        <SummaryCard
          label="Baselines"
          value={String(Array.isArray(metrics?.baselines) ? metrics.baselines.length : 0)}
          detail="naive simple / seasonal"
        />
      </section>
      <section className="technical-grid">
        <article>
          <h2>Evaluacion temporal</h2>
          <p>
            La defensa tecnica debe apoyarse en backtesting por fecha y comparacion contra baselines. Esta vista reserva
            espacio para MAE, RMSE, WAPE y sMAPE por linea, estacion y dia.
          </p>
        </article>
        <article>
          <h2>Explicabilidad</h2>
          <p>
            SHAP o permutation importance se mostraran si existen artefactos. Los factores se describen como
            influencia estimada, no como causalidad.
          </p>
        </article>
        <article>
          <h2>Versionado</h2>
          <p>
            El adaptador lee modelos y metricas desde ml_pipeline en modo solo lectura, manteniendo version de
            dataset y ruta de artefacto.
          </p>
        </article>
      </section>
      <section className="raw-panel">
        <h2>
          <FileSpreadsheet size={18} />
          Registry snapshot
        </h2>
        <pre>{JSON.stringify(metrics, null, 2)}</pre>
      </section>
    </main>
  );
}
export default MetricsView;
