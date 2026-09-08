"use client";

import { captureException } from "@sentry/react";
import { useEffect } from "react";

export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { captureException(error); }, [error]);

  return (
    <main role="alert" style={{ padding: "2rem" }}>
      <h1>Não foi possível exibir esta página</h1>
      <p>Tente carregar a página novamente.</p>
      <button type="button" onClick={reset}>Tentar novamente</button>
    </main>
  );
}
