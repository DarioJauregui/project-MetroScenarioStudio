export function SummaryCard(props: { label: string; value: string; detail?: string }) {
  return (
    <article className="summary-card">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      {props.detail ? <small>{props.detail}</small> : null}
    </article>
  );
}
