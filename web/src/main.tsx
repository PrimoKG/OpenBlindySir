import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <StrictMode>
      <main>
        <h1>OpenBlindySir</h1>
        <p>En construction.</p>
      </main>
    </StrictMode>,
  );
}
