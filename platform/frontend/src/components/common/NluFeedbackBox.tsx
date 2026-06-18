import { CheckCircle2, CircleAlert } from "lucide-react";
import type { NluFeedback } from "../../types";

export function NluFeedbackBox(props: { feedback: NluFeedback }) {
  const icon = props.feedback.tone === "success" ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />;
  return (
    <div className={`nlu-feedback ${props.feedback.tone}`}>
      <strong>
        {icon}
        {props.feedback.tone === "success" ? "Cambios aplicados al formulario" : "No aplicado"}
      </strong>
      {props.feedback.applied.length ? (
        <ul>
          {props.feedback.applied.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      {props.feedback.messages.length ? (
        <ul>
          {props.feedback.messages.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
