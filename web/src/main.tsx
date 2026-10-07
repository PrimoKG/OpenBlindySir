import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./styles.css";
import "./finale.css";
import "./experience.css";
import "./desktop.css";
import "./refinements.css";
import { getLanguage } from "./i18n";

document.documentElement.lang = getLanguage();

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
