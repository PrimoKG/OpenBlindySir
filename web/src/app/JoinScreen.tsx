import { type FormEvent, useState } from "react";
import { t, tCode } from "../i18n";
import { api } from "../net/api";
import { Brand, Button, RecordMark } from "../ui/components";
import { LanguageChoice } from "../ui/LanguageChoice";

export function JoinScreen(props: {
  readonly onJoined: () => void;
  readonly notice?: string | null;
}) {
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recover, setRecover] = useState(false);
  const [code, setCode] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    const result = recover
      ? await api.recover(password, code.toUpperCase())
      : await api.join(password, nickname);
    setBusy(false);
    if (result.ok || result.error === "already_joined") {
      props.onJoined();
    } else {
      setError(tCode("error", result.error));
    }
  };

  return (
    <div className="entry-page">
      <header className="entry-header">
        <Brand />
        <LanguageChoice />
        <span className="muted">{t("join.tagline")}</span>
      </header>
      <main className="entry-layout">
        <section className="entry-intro">
          <p className="eyebrow">{t("join.eyebrow")}</p>
          <h1>{t("join.headline")}</h1>
          <p className="entry-description">{t("join.description")}</p>
          <div className="entry-record">
            <RecordMark size="large" />
            <span>{t("join.recordLabel")}</span>
          </div>
          <ol className="game-steps">
            <li>{t("join.listen")}</li>
            <li>{t("join.guess")}</li>
            <li>{t("join.lockIn")}</li>
          </ol>
        </section>
        <section className="join-panel" aria-labelledby="join-title">
          {props.notice && (
            <p className="notice" role="status">
              {props.notice}
            </p>
          )}
          <form onSubmit={submit} className="stack" aria-busy={busy}>
            <p className="eyebrow">{t("join.formEyebrow")}</p>
            <h2 id="join-title">{t("join.title")}</h2>
            <p className="muted">{t("join.hint")}</p>
            {!recover && (
              <label>
                {t("join.nickname")}
                <input
                  value={nickname}
                  maxLength={24}
                  autoComplete="nickname"
                  onChange={(e) => setNickname(e.target.value)}
                  required
                  placeholder={t("join.nicknamePlaceholder")}
                />
              </label>
            )}
            {recover && (
              <label>
                {t("session.recoveryCode")}
                <input
                  required
                  pattern="[A-Za-z2-9]{6}"
                  maxLength={6}
                  autoComplete="off"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                />
              </label>
            )}
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
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <Button type="submit" kind="primary" disabled={busy}>
              {busy ? t("join.busy") : t("join.submit")}
            </Button>
          </form>
          <Button
            onClick={() => {
              setRecover(!recover);
              setError(null);
            }}
          >
            {t(recover ? "session.newPlace" : "session.recovery")}
          </Button>
          <p className="join-host-link">
            <a href="/host">{t("join.hostLink")}</a>
          </p>
        </section>
      </main>
      <footer className="entry-footer">{t("join.footer")}</footer>
    </div>
  );
}

export function HostGate(props: { readonly onElevated: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    const result = await api.elevate(password);
    setBusy(false);
    if (result.ok) {
      props.onElevated();
    } else {
      setError(tCode("error", result.error));
    }
  };

  return (
    <div className="entry-page">
      <header className="entry-header">
        <Brand />
      </header>
      <main className="host-gate">
        <form onSubmit={submit} className="stack join-panel" aria-busy={busy}>
          <p className="eyebrow">{t("host.eyebrow")}</p>
          <h1>{t("host.gateTitle")}</h1>
          <p className="muted">{t("host.gateHint")}</p>
          <label>
            {t("host.password")}
            <input
              type="password"
              autoComplete="current-password"
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
          <Button type="submit" kind="primary" disabled={busy}>
            {busy ? t("join.busy") : t("host.submit")}
          </Button>
          <a href="/">{t("host.backToGame")}</a>
        </form>
      </main>
    </div>
  );
}
