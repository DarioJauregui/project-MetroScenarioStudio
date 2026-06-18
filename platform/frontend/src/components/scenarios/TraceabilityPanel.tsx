import { useState } from "react";
import { Sparkles, LoaderCircle } from "lucide-react";
import type { ExecutionResult, LlmParseResult, AuditEvent, ExcelArtifact } from "../../types";
import { SectionTitle } from "../common/SectionTitle";
import { TraceList } from "../common/TraceList";
import { DataTable } from "../common/DataTable";

export function TraceabilityPanel(props: {
  result: ExecutionResult | null;
  llmResult: LlmParseResult | null;
  acceptedLlm: boolean;
  auditEvents: AuditEvent[];
  artifacts: ExcelArtifact[];
  exportPath: string | null;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const modified = props.result?.execution?.input?.manual_overrides ?? [];
  return (
    <section className="trace-panel">
      <SectionTitle
        icon={<Sparkles size={19} />}
        title="Explicacion y trazabilidad"
        subtitle="Que se uso, que se modifico y que quedo fuera"
      />
      {!props.result ? (
        <p className="muted">Aparecera despues de ejecutar o importar una prediccion.</p>
      ) : (
        <div className="trace-stack">
          <article className="narrative-summary-card">
            <div className="narrative-summary-heading">
              <Sparkles size={17} />
              <span>Lectura explicativa de la prediccion</span>
            </div>
            {props.result.narrative_summary === "__GENERATING__" ? (
              <div className="generating-explanation">
                <LoaderCircle className="spin-icon" size={20} />
                <span>Generando explicación y análisis con IA...</span>
              </div>
            ) : (
              <div className="narrative-text-container">
                <p>
                  {(() => {
                    const text = props.result.narrative_summary?.trim() || "";
                    if (!text) {
                      return "No hay resumen narrativo disponible para esta ejecucion. La trazabilidad tecnica se mantiene en las tarjetas inferiores.";
                    }
                    if (text.length <= 400 || isExpanded) {
                      return text;
                    }
                    return text.slice(0, 400) + "...";
                  })()}
                </p>
                {props.result.narrative_summary && props.result.narrative_summary.trim().length > 400 && (
                  <button
                    type="button"
                    className="toggle-expand-button"
                    onClick={() => setIsExpanded(!isExpanded)}
                  >
                    {isExpanded ? "Mostrar menos" : "Mostrar más"}
                  </button>
                )}
              </div>
            )}
          </article>
          <div className="trace-grid">
            <TraceList
              title="Variables usadas"
              items={(props.result?.explanations ?? [])
                .filter((item) => item?.used_by_model)
                .map((item) => item?.label ?? "")}
            />
            <TraceList
              title="Modificadas manualmente"
              items={(modified ?? []).map((item) => `${item?.type ?? "variable"} ${item?.field ?? ""}`)}
              muted={!modified?.length}
            />
            <TraceList
              title="Texto libre"
              items={
                props.acceptedLlm
                  ? props.llmResult?.detected_items?.map((item) => `${item?.type ?? "item"} ${item?.name ?? ""}`) ?? []
                  : []
              }
              muted={!props.acceptedLlm}
            />
            <TraceList
              title="Ignorado"
              items={props.llmResult?.not_used?.map((item) => `${item?.text ?? ""}: ${item?.reason ?? ""}`) ?? []}
              muted
            />
          </div>
        </div>
      )}
      {props.result && (props.auditEvents.length || props.artifacts.length || props.exportPath) ? (
        <details className="trace-details">
          <summary>Ver auditoria y artefactos</summary>
          <DataTable rows={props.auditEvents} columns={["timestamp", "action", "summary"]} />
          <DataTable rows={props.artifacts} columns={["artifact_type", "path", "checksum"]} />
        </details>
      ) : null}
    </section>
  );
}
