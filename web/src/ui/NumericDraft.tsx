import { useEffect, useRef, useState } from "react";
import { t } from "../i18n";

/** Keep incomplete typing local and wait for the server echo before allowing publication. */
export function NumericDraft(props: {
  readonly value: number;
  readonly label: string;
  readonly onCommit: (value: number) => boolean;
  readonly onBusy: (busy: boolean) => void;
  readonly disabled?: boolean;
}) {
  const [text, setText] = useState(String(props.value));
  const [error, setError] = useState<"integer" | "save" | null>(null);
  const [awaiting, setAwaiting] = useState(false);
  const editing = useRef(false);
  const requested = useRef<number | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef(props);
  latest.current = props;
  useEffect(() => {
    if (requested.current === props.value) {
      requested.current = null;
      setAwaiting(false);
      setError(null);
      window.clearTimeout(timer.current);
      latest.current.onBusy(false);
    }
    if (!editing.current && requested.current === null) setText(String(props.value));
  }, [props.value]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const commit = () => {
    if (requested.current !== null) return;
    editing.current = false;
    if (!/^-?\d+$/.test(text) || !Number.isInteger(Number(text)) || Math.abs(Number(text)) > 1000) {
      setError("integer");
      props.onBusy(true);
      return;
    }
    const value = Number(text);
    setError(null);
    if (value === props.value) {
      props.onBusy(false);
      // Zero is an explicit review decision, even if it was the initial value.
      props.onCommit(value);
      return;
    }
    requested.current = value;
    setAwaiting(true);
    props.onBusy(true);
    if (!props.onCommit(value)) {
      requested.current = null;
      setAwaiting(false);
      setError("save");
      props.onBusy(false);
      return;
    }
    timer.current = window.setTimeout(() => {
      requested.current = null;
      setAwaiting(false);
      setError("save");
      setText(String(latest.current.value));
      latest.current.onBusy(false);
    }, 10000);
  };
  return (
    <span className="numeric-draft">
      <input
        type="text"
        inputMode="numeric"
        className="points"
        aria-label={props.label}
        aria-invalid={!!error || undefined}
        value={text}
        disabled={props.disabled || awaiting}
        onFocus={() => {
          editing.current = true;
        }}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
          props.onBusy(true);
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.currentTarget.blur();
          }
        }}
      />
      {error && (
        <small role="alert" className="error">
          {t(error === "integer" ? "ux.integerError" : "ux.saveTimeout")}
        </small>
      )}
    </span>
  );
}
