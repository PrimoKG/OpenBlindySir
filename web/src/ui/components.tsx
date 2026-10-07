// Small accessible building blocks: real buttons, text+icon statuses, native dialogs.
import { type ButtonHTMLAttributes, type ReactNode, useEffect, useId, useRef } from "react";
import { t } from "../i18n";
import type { AudioState, ConnectionState } from "../protocol";
import { LanguageChoice } from "./LanguageChoice";

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
        <LanguageChoice />
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
  readonly title?: string;
  readonly children?: ReactNode;
  readonly open: boolean;
  readonly message: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
  readonly cancelLabel?: string;
  readonly confirmLabel?: string;
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
        event.stopPropagation();
        props.onCancel();
      }}
      className="dialog"
      aria-labelledby={titleId}
      aria-describedby={messageId}
    >
      <h2 id={titleId}>{props.title ?? t("hostui.confirmTitle")}</h2>
      <p id={messageId}>{props.message}</p>
      {props.children}
      <div className="row">
        <Button onClick={props.onCancel}>{props.cancelLabel ?? t("hostui.cancel")}</Button>
        <Button kind="primary" onClick={props.onConfirm}>
          {props.confirmLabel ?? t("hostui.confirm")}
        </Button>
      </div>
    </dialog>
  );
}

/** Native modal: focus containment, Escape, and return to the opening control. */
export function Modal(props: {
  readonly open: boolean;
  readonly title: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
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
  useEffect(() => {
    if (!props.open) return;
    const previous = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = previous;
    };
  }, [props.open]);
  return (
    <dialog
      ref={ref}
      className="dialog workspace-modal"
      aria-label={props.title}
      onCancel={(event) => {
        event.preventDefault();
        event.stopPropagation();
        props.onClose();
      }}
    >
      <header className="modal-heading">
        <h2 id={titleId}>{props.title}</h2>
        <Button onClick={props.onClose} aria-label={t("flow.close")}>
          ×
        </Button>
      </header>
      {props.children}
    </dialog>
  );
}

export function Tabs(props: {
  readonly id: string;
  readonly tabs: readonly { id: string; label: string }[];
  readonly value: string;
  readonly onChange: (id: string) => void;
}) {
  const id = props.id;
  return (
    <div className="tabs" role="tablist" aria-label={t("flow.sections")}>
      {props.tabs.map((tab, index) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`${id}-${tab.id}`}
          aria-controls={`${id}-panel-${tab.id}`}
          aria-selected={tab.id === props.value}
          tabIndex={tab.id === props.value ? 0 : -1}
          onClick={() => props.onChange(tab.id)}
          onKeyDown={(event) => {
            let next: number;
            if (event.key === "ArrowRight") next = (index + 1) % props.tabs.length;
            else if (event.key === "ArrowLeft")
              next = (index + props.tabs.length - 1) % props.tabs.length;
            else if (event.key === "Home") next = 0;
            else if (event.key === "End") next = props.tabs.length - 1;
            else return;
            event.preventDefault();
            const target = props.tabs[next];
            if (target) {
              props.onChange(target.id);
              document.getElementById(`${id}-${target.id}`)?.focus();
            }
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
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
