import { useState } from "react";
import { t, tCode } from "../i18n";
import { api } from "../net/api";
import type { HostView } from "../protocol";
import { Button, ConfirmDialog } from "../ui/components";

export function BridgeConnections({ view }: { readonly view: HostView }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const revoke = async () => {
    if (!selected || busy) return;
    const id = selected;
    setSelected(null);
    setBusy(true);
    const result = await api.revokeBridge(id);
    setBusy(false);
    if (result.ok) {
      setNotice(t("bridges.revoked"));
      setError(null);
    } else setError(tCode("error", result.error));
  };
  return (
    <details className="disclosure bridge-connections">
      <summary>
        {t("bridges.heading")} ({view.host.bridges.length})
      </summary>
      <div className="stack" aria-busy={busy}>
        <p className="muted">{t("bridges.credentialsHint")}</p>
        {view.host.bridges.length === 0 && <p>{t("bridges.empty")}</p>}
        <ul className="list">
          {view.host.bridges.map((bridge) => (
            <li key={bridge.bridge_id} className="stack bridge-card">
              <strong>{bridge.name}</strong>
              <p>
                {t(`bridges.${bridge.state}`)} ·{" "}
                {t("bridges.tracks", { count: bridge.track_count })} ·{" "}
                {t("bridges.jobs", { count: bridge.jobs_in_flight })}
              </p>
              <p className="muted">
                {bridge.version} ·{" "}
                {t("bridges.protocol", { min: bridge.protocol, max: bridge.protocol })} ·{" "}
                {bridge.formats.join(", ")}
              </p>
              <p className="muted">{bridge.bridge_id}</p>
              {bridge.state === "OFFLINE" && <p className="notice">{t("bridges.offlineHint")}</p>}
              {bridge.source_error && (
                <p className="error">{tCode("error", bridge.source_error)}</p>
              )}
              <Button
                kind="danger"
                disabled={busy}
                onClick={() => setSelected(bridge.bridge_id)}
                aria-label={t("bridges.revokeNamed", { name: bridge.name })}
              >
                {t("bridges.revoke")}
              </Button>
            </li>
          ))}
        </ul>
        {notice && <p role="status">{notice}</p>}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </div>
      <ConfirmDialog
        open={selected !== null}
        message={t("bridges.revokeConfirm")}
        onCancel={() => setSelected(null)}
        onConfirm={() => void revoke()}
      />
    </details>
  );
}
