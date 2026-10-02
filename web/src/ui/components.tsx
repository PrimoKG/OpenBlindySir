// Small accessible building blocks: real buttons, text+icon statuses, native dialogs.
import { type ReactNode, useEffect, useRef } from "react";
import { t } from "../i18n";
import type { AudioState, ConnectionState } from "../protocol";

export function Button(props: {
  readonly children: ReactNode;
  readonly onClick?: () => void;
  readonly disabled?: boolean;
  readonly kind?: "primary" | "secondary" | "danger";
  readonly type?: "button" | "submit";
}) {
  return (
    <button
      type={props.type ?? "button"}
      className={`btn btn-${props.kind ?? "secondary"}`}
      onClick={props.onClick}
      disabled={props.disabled}
    >
      {props.children}
    </button>
  );
}

/** Status always as text + icon, never colour alone (spec §5.1). */
export function AudioBadge(props: {
  readonly state: AudioState;
  readonly connection?: ConnectionState;
}) {
  if (props.connection && props.connection !== "ONLINE") {
    return <span className="badge badge-off">{t("status.offline")}</span>;
  }
  const label = {
    READY: t("status.ready"),
    LOADING: t("status.loading"),
    LOCKED: t("status.locked"),
    ERROR: t("status.error"),
    IDLE: t("status.idle"),
    PLAYING: t("status.playing"),
  }[props.state];
  return <span className={`badge badge-${props.state.toLowerCase()}`}>{label}</span>;
}

export function LiveRegion(props: { readonly children: ReactNode; readonly assertive?: boolean }) {
  return (
    <div aria-live={props.assertive ? "assertive" : "polite"} className="live">
      {props.children}
    </div>
  );
}

export function ConfirmDialog(props: {
  readonly open: boolean;
  readonly message: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) {
      return;
    }
    if (props.open && !dialog.open) {
      dialog.showModal();
    } else if (!props.open && dialog.open) {
      dialog.close();
    }
  }, [props.open]);
  return (
    <dialog ref={ref} onCancel={props.onCancel} className="dialog">
      <p>{props.message}</p>
      <div className="row">
        <Button kind="primary" onClick={props.onConfirm}>
          {t("hostui.confirm")}
        </Button>
        <Button onClick={props.onCancel}>{t("hostui.cancel")}</Button>
      </div>
    </dialog>
  );
}

export function Toast(props: { readonly text: string; readonly onClose: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(props.onClose, 4000);
    return () => window.clearTimeout(timer);
  }, [props.onClose]);
  return (
    <div className="toast" role="status">
      {props.text}
    </div>
  );
}
