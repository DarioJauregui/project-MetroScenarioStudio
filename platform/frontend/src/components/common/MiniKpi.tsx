export function MiniKpi(props: { label: string; value: string; prominent?: boolean }) {
  return (
    <article className={props.prominent ? "mini-kpi prominent" : "mini-kpi"}>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </article>
  );
}
