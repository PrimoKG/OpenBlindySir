// Small accessible building blocks: real buttons, text+icon statuses, native dialogs.
import { type ButtonHTMLAttributes, type ReactNode, useEffect, useId, useRef } from "react";
import { t } from "../i18n";
import type { AudioState, ConnectionState } from "../protocol";

export function Button(
  props: ButtonHTMLAttributes<HTMLButtonElement> & {
    readonly children: ReactNode;
    readonly kind?: "primary" | "secondary" | "danger";
  },
) {
  const { kind = "secondary", className = "", children, ...buttonProps } = props;
  return (
    <button
      {...buttonProps}
      type={props.type ?? "button"}
      className={`btn btn-${kind} ${className}`}
    >
      {children}
    </button>
  );
}

/** A record is the shared visual signature; decorative, without an icon dependency. */
export function RecordMark(props: {
  readonly size?: "small" | "large";
  readonly playing?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={`record record-${props.size ?? "small"} ${props.playing ? "record-playing" : ""}`}
    />
  );
}

export function Brand() {
  return (
    <span className="brand">
      <RecordMark />
      <strong>{t("app.title")}</strong>
    </span>
  );
}

export function StageMessage(props: {
  readonly title: string;
  readonly description?: string | undefined;
  readonly children?: ReactNode;
  readonly busy?: boolean;
}) {
  return (
    <section className="stage-message" aria-busy={props.busy || undefined}>
      <RecordMark size="large" />
      <LiveRegion>
        <h1>{props.title}</h1>
      </LiveRegion>
      {props.description && <p className="muted stage-description">{props.description}</p>}
      {props.children}
    </section>
  );
}

export function ConnectionScreen(props: {
  readonly title: string;
  readonly description?: string;
  readonly children?: ReactNode;
}) {
  return (
    <div className="entry-page">
      <header className="entry-header">
        <Brand />
      </header>
      <main className="connection-screen">
        <StageMessage title={props.title} description={props.description}>
          {props.children}
        </StageMessage>
      </main>
    </div>
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
  const titleId = useId();
  const messageId = useId();
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) {
      return;
    }
    if (props.open && !dialog.open) {
      opener.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
      dialog.querySelector<HTMLButtonElement>("button")?.focus();
    } else if (!props.open && dialog.open) {
      dialog.close();
      if (opener.current?.isConnected) opener.current.focus();
    }
  }, [props.open]);
  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        props.onCancel();
      }}
      className="dialog"
      aria-labelledby={titleId}
      aria-describedby={messageId}
    >
      <h2 id={titleId}>{t("hostui.confirmTitle")}</h2>
      <p id={messageId}>{props.message}</p>
      <div className="row">
        <Button onClick={props.onCancel}>{t("hostui.cancel")}</Button>
        <Button kind="primary" onClick={props.onConfirm}>
          {t("hostui.confirm")}
        </Button>
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
      <span>{props.text}</span>
      <Button aria-label={t("app.dismiss")} onClick={props.onClose}>
        ×
      </Button>
    </div>
  );
}
