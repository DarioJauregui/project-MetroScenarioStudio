import { BarChart3, CircleAlert, Info } from "lucide-react";
import type { ScenarioComparison, ScenarioExecution } from "../../types";
import { formatNumber, formatPercent } from "../../utils/formatters";
import { SectionTitle } from "../common/SectionTitle";

export function ComparisonPanel(props: {
  enabled: boolean;
  history: ScenarioExecution[];
  baseId: string;
  candidateId: string;
  comparison: ScenarioComparison | null;
  warning: string | null;
  onToggle: (enabled: boolean) => void;
  onBaseChange: (id: string) => void;
  onCandidateChange: (id: string) => void;
  onCompare: () => void;
  onOpenDiff: () => void;
}) {
  const network = props.comparison?.rows.find((row) => row.level === "network");
  return (
    <section className="comparison-box">
      <div className="section-heading comparison-header">
        <div className="comparison-title-group">
          <SectionTitle
            icon={<BarChart3 size={19} />}
            title="Comparación de escenarios"
            subtitle="Desactivada por defecto para evitar interpretaciones causales"
          />
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={props.enabled}
              onChange={(event) => props.onToggle(event.target.checked)}
            />
            <span className="slider"></span>
            <span className="toggle-label">{props.enabled ? "ON" : "OFF"}</span>
          </label>
        </div>
      </div>
      {props.enabled ? (
        <div className="comparison-body-layout">
          <div className="comparison-left-col">
            <div className="comparison-controls">
              <label>
                Predicción base
                <select value={props.baseId} onChange={(event) => props.onBaseChange(event.target.value)}>
                  <option value="">Selecciona base</option>
                  {props.history.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id} - {item.status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Predicción comparativa
                <select value={props.candidateId} onChange={(event) => props.onCandidateChange(event.target.value)}>
                  <option value="">Selecciona candidata</option>
                  {props.history.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id} - {item.status}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" onClick={props.onCompare}>
                Comparar
              </button>
            </div>
            {props.warning ? (
              <div className="inline-warning">
                <CircleAlert size={18} />
                {props.warning}
              </div>
            ) : null}
            {props.comparison?.notes.map((note) => (
              <p key={note} className="muted comparison-note">
                {note}
              </p>
            ))}
          </div>
          <div className="comparison-right-col">
            {network ? (
              <div className="delta-card">
                <span>Diferencia total</span>
                <strong>{formatNumber(network.delta_abs)}</strong>
                <small>{formatPercent(network.delta_pct)} respecto a la base</small>
              </div>
            ) : null}
            {props.comparison ? (
              <button type="button" onClick={props.onOpenDiff} className="diff-details-btn">
                <Info size={18} />
                Ver diferencias de configuracion
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
