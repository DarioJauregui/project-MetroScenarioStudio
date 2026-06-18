import { columnLabel, formatTableCell } from "../../utils/formatters";

export function DataTable(props: { rows: object[]; columns: string[] }) {
  if (!props.rows.length) return <p className="muted">Sin datos que mostrar.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {props.columns.map((column) => (
              <th key={column}>{columnLabel(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rows.map((row, index) => (
            <tr key={index}>
              {props.columns.map((column) => (
                <td key={column}>
                  {formatTableCell(column, (row as Record<string, unknown>)[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
