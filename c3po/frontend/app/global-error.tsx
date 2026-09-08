"use client";

import { captureException } from "@sentry/react";
import { useEffect } from "react";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { captureException(error); }, [error]);

  return (
    <html lang="pt-BR">
      <body>
        <main role="alert" style={{ padding: "2rem", fontFamily: "sans-serif" }}>
          <h1>Não foi possível abrir o C3PO</h1>
          <p>Tente carregar a página novamente.</p>
          <button type="button" onClick={reset}>Tentar novamente</button>
        </main>
      </body>
    </html>
  );
}
