import { type FormEvent, useState } from "react";
import { t, tCode } from "../i18n";
import { api } from "../net/api";
import { Button } from "../ui/components";

export function JoinScreen(props: { readonly onJoined: () => void }) {
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    const result = await api.join(password, nickname);
    setBusy(false);
    if (result.ok || result.error === "already_joined") {
      props.onJoined();
    } else {
      setError(tCode("error", result.error));
    }
  };

  return (
    <main className="center narrow">
      <h1>{t("app.title")}</h1>
      <form onSubmit={submit} className="stack">
        <h2>{t("join.title")}</h2>
        <label>
          {t("join.password")}
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <label>
          {t("join.nickname")}
          <input
            value={nickname}
            maxLength={24}
            autoComplete="nickname"
            onChange={(e) => setNickname(e.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <Button type="submit" kind="primary" disabled={busy}>
          {t("join.submit")}
        </Button>
      </form>
    </main>
  );
}

export function HostGate(props: { readonly onElevated: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const result = await api.elevate(password);
    if (result.ok) {
      props.onElevated();
    } else {
      setError(tCode("error", result.error));
    }
  };

  return (
    <main className="center narrow">
      <h1>{t("app.title")}</h1>
      <form onSubmit={submit} className="stack">
        <h2>{t("host.gateTitle")}</h2>
        <label>
          {t("host.password")}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <Button type="submit" kind="primary">
          {t("host.submit")}
        </Button>
        <a href="/">{t("host.backToGame")}</a>
      </form>
    </main>
  );
}
