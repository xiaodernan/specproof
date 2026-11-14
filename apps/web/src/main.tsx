import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { I18nProvider } from "./i18n";
import "./theme/tokens.css";
import "./styles/base.css";
import "./styles/aurora.css";
import "./styles/viz.css";
import "./styles/print.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>
);
import "./styles/product.css";
