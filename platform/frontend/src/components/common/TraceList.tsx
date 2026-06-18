import { CheckCircle2 } from "lucide-react";

export function TraceList(props: { title: string; items: string[]; muted?: boolean }) {
  const items = props.items.length ? props.items : ["Sin elementos registrados"];
  return (
    <article className={props.muted ? "trace-list muted-list" : "trace-list"}>
      <h3>{props.title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>
            <CheckCircle2 size={15} />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
