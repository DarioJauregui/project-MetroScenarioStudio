import type { ReactNode } from "react";
import { Info } from "lucide-react";

export function SectionTitle(props: { icon: ReactNode; title: string; subtitle?: string }) {
  return (
    <div className="section-title">
      <h2>
        {props.icon}
        {props.title}
        {props.subtitle ? (
          <span className="info-tooltip inline-info" tabIndex={0}>
            <Info size={15} />
            <span role="tooltip">{props.subtitle}</span>
          </span>
        ) : null}
      </h2>
    </div>
  );
}
