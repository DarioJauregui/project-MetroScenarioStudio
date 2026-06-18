import { statusLabel } from "../../utils/formatters";

export function StatusBadge(props: { value: string }) {
  return <span className={`status-badge ${props.value}`}>{statusLabel(props.value)}</span>;
}
