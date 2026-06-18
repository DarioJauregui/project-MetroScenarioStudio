import type { ReactNode } from "react";

export function Accordion(props: { icon: ReactNode; title: string; badge?: string; children: ReactNode }) {
  return (
    <details className="accordion" open>
      <summary>
        <span>
          {props.icon}
          {props.title}
        </span>
        {props.badge ? <small>{props.badge}</small> : null}
      </summary>
      <div className="accordion-body">{props.children}</div>
    </details>
  );
}
