import { X } from "lucide-react";
import type { ExecutionResult } from "../../types";
import { DataTable } from "../common/DataTable";

export function ComparisonDiffModal(props: {
  baseResult: ExecutionResult | null;
  candidateResult: ExecutionResult | null;
  onClose: () => void;
}) {
  const baseInput = props.baseResult?.execution?.input;
  const candidateInput = props.candidateResult?.execution?.input;
  const rows = [
    {
      campo: "Rango",
      base: props.baseResult?.execution
        ? `${props.baseResult.execution.range_start} - ${props.baseResult.execution.range_end}`
        : "",
      comparativa: props.candidateResult?.execution
        ? `${props.candidateResult.execution.range_start} - ${props.candidateResult.execution.range_end}`
        : "",
    },
    {
      campo: "Estado",
      base: props.baseResult?.execution?.status ?? "",
      comparativa: props.candidateResult?.execution?.status ?? "",
    },
    {
      campo: "Cambios manuales",
      base: String(baseInput?.manual_overrides?.length ?? 0),
      comparativa: String(candidateInput?.manual_overrides?.length ?? 0),
    },
    {
      campo: "Texto libre aceptado",
      base: String(baseInput?.llm_accepted_items?.length ?? 0),
      comparativa: String(candidateInput?.llm_accepted_items?.length ?? 0),
    },
  ];
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <section className="modal">
        <div className="section-heading">
          <h2>Diferencias de configuracion</h2>
          <button type="button" className="icon-button" onClick={props.onClose} title="Cerrar">
            <X size={18} />
          </button>
        </div>
        <DataTable rows={rows} columns={["campo", "base", "comparativa"]} />
      </section>
    </div>
  );
}
