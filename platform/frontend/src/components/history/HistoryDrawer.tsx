import { useState } from "react";
import type { RefObject } from "react";
import { History, Upload, X } from "lucide-react";
import type { ScenarioExecution } from "../../types";
import { formatDateTime } from "../../utils/formatters";
import { SectionTitle } from "../common/SectionTitle";
import { StatusBadge } from "../common/StatusBadge";

export function HistoryDrawer(props: {
  history: ScenarioExecution[];
  importInputRef: RefObject<HTMLInputElement | null>;
  onClose: () => void;
  onImportClick: () => void;
  onImport: (file: File | null) => void;
  onOpen: (id: string) => void;
  onDerive: (id: string) => void;
}) {
  const [width, setWidth] = useState(520);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = width;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = startX - moveEvent.clientX; // drag left increases width
      const newWidth = Math.max(320, Math.min(1200, startWidth + deltaX));
      setWidth(newWidth);
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  };

  return (
    <>
      <div className="drawer-backdrop" onClick={props.onClose} />
      <aside className="history-drawer" style={{ width: `${width}px` }} aria-label="Predicciones guardadas">
        <div className="drawer-resize-handle" onMouseDown={handleMouseDown} />
        <div className="section-heading">
          <SectionTitle
            icon={<History size={19} />}
            title="Predicciones"
            subtitle="Historial visual. En una version posterior se filtrara por usuario autenticado."
          />
          <button type="button" className="icon-button" onClick={props.onClose} title="Cerrar predicciones">
            <X size={18} />
          </button>
        </div>
        <div className="history-actions">
          <p>Formato admitido: Excel estructurado de Metro Scenario Studio con hoja metadata_json.</p>
          <button type="button" onClick={props.onImportClick}>
            <Upload size={18} />
            Importar prediccion
          </button>
        </div>
        <input
          ref={props.importInputRef}
          className="visually-hidden"
          type="file"
          accept=".xlsx"
          onChange={(event) => {
            props.onImport(event.target.files?.[0] ?? null);
            event.currentTarget.value = "";
          }}
        />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Tipo</th>
                <th>Rango</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {props.history.slice(0, 10).map((item) => (
                <tr key={item.id}>
                  <td>{formatDateTime(item.executed_at ?? item.created_at ?? "")}</td>
                  <td>
                    <StatusBadge value={item.status} />
                  </td>
                  <td>
                    {item.range_start} - {item.range_end}
                  </td>
                  <td className="table-actions">
                    <button type="button" onClick={() => props.onOpen(item.id)}>
                      Abrir referencia
                    </button>
                    <button type="button" onClick={() => props.onDerive(item.id)}>
                      Crear derivada
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </aside>
    </>
  );
}
