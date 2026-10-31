"use client";

import { useEffect, useMemo, useState } from "react";

type BadgeName = "price" | "market_cap" | "liquidity";
type BadgeStatus = "passed" | "below_minimum" | "missing";
interface ListedItem {
  symbol: string;
  name: string;
  valuation_status: "valued" | "not_evaluable";
  not_evaluable_reasons: string[];
  price: number | null;
  our_tp: number | null;
  buy_in: number | null;
  buy_permission: boolean;
  official_generation_id: string | null;
  minimum_badges: Record<BadgeName, { status: BadgeStatus; value: number | null; minimum: number }>;
}
interface ListedResponse {
  universe_size: number;
  item_count: number;
  valued_count: number;
  not_evaluable_count: number;
  etfs_on_existing_path: number;
  classification_pending_count: number;
  classified_equity_count: number;
  catalogue: { received_at: string; source_date: string; source_url: string; manifest_sha256: string };
  items: ListedItem[];
}

const reasons: Record<string, string> = {
  listing_classification_pending: "Classificação do instrumento pendente",
  price_missing: "Preço indisponível",
  canonical_valuation_missing: "Avaliação canônica indisponível",
  canonical_tp_missing: "TP canônico indisponível",
  canonical_provenance_missing: "Proveniência da avaliação indisponível",
  insufficient_history: "Histórico insuficiente",
};
const badges: { name: BadgeName; label: string }[] = [
  { name: "price", label: "Preço" },
  { name: "market_cap", label: "Valor de mercado" },
  { name: "liquidity", label: "Liquidez" },
];
const badgeLabels: Record<BadgeStatus, string> = {
  passed: "Dentro do mínimo", below_minimum: "Abaixo do mínimo", missing: "Dado indisponível",
};
const PAGE_SIZE = 100;

export function ListedUniverse({ market, apiUrl, module }: {
  market: "B3" | "NASDAQ" | "NYSE";
  apiUrl: string;
  module: "candidates" | "matrix-power";
}) {
  const [data, setData] = useState<ListedResponse | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<{ name: BadgeName | "all"; status: BadgeStatus }>({ name: "all", status: "passed" });
  const [page, setPage] = useState(0);

  useEffect(() => {
    let current = true;
    setData(null);
    setError("");
    setPage(0);
    const load = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/${module}/${market.toLowerCase()}/universe`, {
          cache: "no-store", credentials: "include",
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(response.status === 503
          ? "O inventário oficial completo aguarda atualização."
          : "Não foi possível carregar o inventário oficial completo.");
        if (current) setData(payload);
      } catch (failure) {
        if (current) setError(failure instanceof Error ? failure.message : "Inventário indisponível.");
      }
    };
    void load();
    return () => { current = false; };
  }, [apiUrl, market, module]);

  const filtered = useMemo(() => {
    const search = query.trim().toLocaleLowerCase();
    return (data?.items ?? []).filter((item) => (
      (!search || `${item.symbol} ${item.name}`.toLocaleLowerCase().includes(search))
      && (filter.name === "all" || item.minimum_badges[filter.name].status === filter.status)
    ));
  }, [data, query, filter]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: market === "B3" ? "BRL" : "USD" });
  const price = (value: number | null) => value === null ? "—" : currency.format(value);

  return <section className="panel candidate-ranking-panel" aria-label={`Universo completo ${market}`}>
    <details>
      <summary><strong>Universo completo · {market}</strong>{data ? ` · ${data.universe_size} instrumentos` : ""}</summary>
      <p>Todos os nomes do inventário oficial, incluindo os que ainda não podem ser avaliados. Os mínimos abaixo são filtros opcionais; a compra exige liberação PIT e as portas do decisor. ETFs seguem na seleção existente.</p>
      {error ? <p role="status">{error}</p> : !data ? <p role="status">Carregando inventário oficial…</p> : <>
        <p>{data.valued_count} avaliados · {data.not_evaluable_count} não avaliáveis · arquivo de {data.catalogue.source_date.slice(0, 10).split("-").reverse().join("/")} · recebido em {new Date(data.catalogue.received_at).toLocaleString("pt-BR")}</p>
        {data.classification_pending_count > 0 && <p role="status">{data.classification_pending_count} instrumentos aguardam classificação. Eles continuam visíveis, sem liberação de compra; a seleção existente de ETFs permanece separada.</p>}
        <div className="research-market-tabs" style={{ flexWrap: "wrap", gap: 12 }}>
          <label>Buscar ação <input aria-label="Buscar no universo completo" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} /></label>
          <label>Mínimo <select value={filter.name} onChange={(event) => { setFilter({ ...filter, name: event.target.value as BadgeName | "all" }); setPage(0); }}>
            <option value="all">Sem filtro</option>{badges.map((badge) => <option key={badge.name} value={badge.name}>{badge.label}</option>)}
          </select></label>
          {filter.name !== "all" && <label>Condição <select value={filter.status} onChange={(event) => { setFilter({ ...filter, status: event.target.value as BadgeStatus }); setPage(0); }}>
            {Object.entries(badgeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>}
        </div>
        <div className="candidate-live-table-wrap">
          <table className="candidate-live-table">
            <thead><tr><th>Ação</th><th>Preço</th><th>TP canônico</th><th>Mínimos</th><th>Avaliação</th><th>Compra</th></tr></thead>
            <tbody>{visible.map((item) => <tr key={item.symbol}>
              <td><strong>{item.symbol}</strong><div>{item.name}</div></td>
              <td>{price(item.price)}</td><td>{price(item.our_tp)}</td>
              <td>{badges.map((badge) => <div key={badge.name} title={`Mínimo: ${currency.format(item.minimum_badges[badge.name].minimum)}`}>
                {badge.label}: {badgeLabels[item.minimum_badges[badge.name].status]}
              </div>)}</td>
              <td>{item.valuation_status === "valued" ? "Avaliado" : <><strong>Não avaliável</strong><div>{item.not_evaluable_reasons.map((reason) => reasons[reason] ?? reason).join(" · ")}</div></>}</td>
              <td>{item.buy_permission ? "Permitida pelo decisor e pelo escopo PIT" : "Sem liberação"}</td>
            </tr>)}</tbody>
          </table>
          {!filtered.length && <p>Nenhum nome corresponde aos filtros. Limpe os filtros para consultar todo o inventário.</p>}
        </div>
        <nav aria-label="Páginas do universo completo" className="research-market-tabs">
          <button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Anterior</button>
          <span>Página {currentPage + 1} de {pageCount} · {filtered.length} de {data.universe_size} nomes</span>
          <button disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}>Próxima</button>
        </nav>
      </>}
    </details>
  </section>;
}
