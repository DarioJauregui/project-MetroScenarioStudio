import type { ReactNode } from "react";
import { CircleAlert, CheckCircle2, X } from "lucide-react";

export function ToastStack(props: {
  error: string | null;
  notice: string | null;
  onCloseError: () => void;
  onCloseNotice: () => void;
}) {
  if (!props.error && !props.notice) return null;
  return (
    <div className="toast-stack" aria-live="polite">
      {props.error ? (
        <Message tone="error" icon={<CircleAlert size={18} />} text={props.error} onClose={props.onCloseError} />
      ) : null}
      {props.notice ? (
        <Message tone="success" icon={<CheckCircle2 size={18} />} text={props.notice} onClose={props.onCloseNotice} />
      ) : null}
    </div>
  );
}

function Message(props: { tone: "success" | "error"; icon: ReactNode; text: string; onClose: () => void }) {
  return (
    <div className={`message ${props.tone}`}>
      {props.icon}
      <span>{props.text}</span>
      <button type="button" className="toast-close" onClick={props.onClose} title="Cerrar aviso">
        <X size={15} />
      </button>
      <i className="toast-timer" />
    </div>
  );
}
