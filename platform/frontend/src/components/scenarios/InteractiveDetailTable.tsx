import { Search } from "lucide-react";
import type { PredictionRow, SortDirection } from "../../types";
import { formatNumber } from "../../utils/formatters";

export function InteractiveDetailTable(props: {
  rows: PredictionRow[];
  filter: string;
  onFilterChange: (value: string) => void;
  sort: { key: keyof PredictionRow; direction: SortDirection };
  onSort: (sort: { key: keyof PredictionRow; direction: SortDirection }) => void;
}) {
  const columns: Array<{ key: keyof PredictionRow; label: string }> = [
    { key: "target_date", label: "Fecha" },
    { key: "linea", label: "Linea" },
    { key: "station_abbrev", label: "Estacion" },
    { key: "y_pred", label: "Viajes previstos" },
    { key: "y_real", label: "Real" },
  ];

  function changeSort(key: keyof PredictionRow) {
    props.onSort({
      key,
      direction: props.sort.key === key && props.sort.direction === "desc" ? "asc" : "desc",
    });
  }

  return (
    <div>
      <label className="search-box">
        <Search size={18} />
        <input
          value={props.filter}
          onChange={(event) => props.onFilterChange(event.target.value)}
          placeholder="Filtrar por linea o estacion"
        />
      </label>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>
                  <button type="button" className="table-sort" onClick={() => changeSort(column.key)}>
                    {column.label}
                    {props.sort.key === column.key ? (props.sort.direction === "desc" ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.rows.slice(0, 80).map((row) => (
              <tr key={`${row.target_date}-${row.series_id}`}>
                <td>{row.target_date}</td>
                <td>{row.linea}</td>
                <td title={row.estacion}>{row.station_abbrev}</td>
                <td>{formatNumber(row.y_pred)}</td>
                <td>{row.y_real ? formatNumber(row.y_real) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
