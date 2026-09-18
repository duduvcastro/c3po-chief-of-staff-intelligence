"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Position = { quantity: string; total_cost: string; value: string | null; profit: string | null; profit_percent: string | null; realized: string; dividends: string };
type Event = { request_id: string; symbol: string; kind: string; effective_date: string; quantity: string; total: string; fees: string; market: string };
type Period = { label: string; start: string; end: string; profit_usd: string | null; return_percent: string | null; reason: string | null };
type Account = { events: Event[]; summary: { positions: Record<string, Position>; complete: boolean; missing: string[]; unconfigured?: string[]; value_usd: string | null; cost_usd: string | null; profit_usd: string | null; profit_percent: string | null } | null; periods: Period[]; fx: { brl_per_usd: string; as_of: string; source: string } | null; generated_at: string; methodology?: string };
type Input = { symbol: string; kind: string; effective_date: string; quantity: string; total: string; fees: string; request_id: string };
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const money = (v: string | number | null | undefined, currency = 'USD') => v == null ? 'N/D' : new Intl.NumberFormat('pt-BR', { style: 'currency', currency }).format(Number(v));
const percent = (v: string | null | undefined) => v == null ? 'N/D' : `${Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`;
const numeric = (value: string) => { const clean = value.trim().replace(/\s/g, ''); return clean.includes(',') ? clean.replace(/\./g, '').replace(',', '.') : clean; };
const kinds: Record<string, string> = { position: 'Posição informada', buy: 'Compra', sell: 'Venda', dividend: 'Provento', split: 'Desdobramento / grupamento' };

export function usePortfolioAccount(apiUrl: string) {
  const [data, setData] = useState<Account | null>(null);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    try {
      const response = await fetch(`${apiUrl}/api/v1/realtime/portfolio/account`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Não foi possível atualizar as posições e os resultados.');
      const next: Account = await response.json();
      if (current === generation.current) { setData(next); setError(''); }
    } catch (e) { if (current === generation.current) setError(e instanceof Error ? e.message : 'Falha na atualização'); }
  }, [apiUrl]);
  useEffect(() => { void load(); const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 60000); return () => { window.clearInterval(timer); generation.current++; }; }, [load]);
  const save = async (input: Input) => {
    const response = await fetch(`${apiUrl}/api/v1/realtime/portfolio/events`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
    if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === 'string' ? body.detail : 'Confira os campos da movimentação.'); }
    await load();
  };
  const cancel = async (id: string) => {
    const response = await fetch(`${apiUrl}/api/v1/realtime/portfolio/events/${id}/void`, { method: 'POST' });
    if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === 'string' ? body.detail : 'Não foi possível cancelar.'); }
    await load();
  };
  return { data, error, load, save, cancel };
}

type Controller = ReturnType<typeof usePortfolioAccount>;

export function PortfolioSummary({ account }: { account: Controller }) {
  const data = account.data, summary = data?.summary;
  return <div className="portfolio-account-summary">
    <div><strong>Resultado da carteira · USD</strong><p>Ganho ou perda em aberto das posições cadastradas. Valores de cada ação continuam na moeda original.</p></div>
    {account.error && <p role="alert">{account.error} Os últimos resultados podem estar desatualizados.</p>}
    {!summary ? <p>Informe a quantidade e o custo total abaixo de cada ação para calcular seu resultado.</p> : <>
      <div className="portfolio-account-cards">
        <div><small>Valor das posições</small><strong>{money(summary.value_usd)}</strong></div>
        <div><small>Custo das posições</small><strong>{money(summary.cost_usd)}</strong></div>
        <div><small>Lucro / prejuízo em aberto</small><strong className={Number(summary.profit_usd) < 0 ? 'change-down' : 'change-up'}>{money(summary.profit_usd)}</strong><span>{percent(summary.profit_percent)}</span></div>
      </div>
      {!!summary.unconfigured?.length && <p>Subtotal das posições informadas. Ainda sem quantidade e custo: {summary.unconfigured.join(', ')}. Cadastre zero para ativos apenas acompanhados.</p>}
      {!summary.complete && <p role="status">Total indisponível: confira cotação ou câmbio de {summary.missing.join(', ')}.</p>}
      {data?.fx && <small>Conversão apenas no consolidado: US$ 1 = {money(data.fx.brl_per_usd, 'BRL')} · {data.fx.source} · {new Date(data.fx.as_of).toLocaleString('pt-BR')}</small>}
      <div className="portfolio-account-cards">{data?.periods.slice(0, 3).map(p => <div key={p.label}><small>{p.label}</small><strong>{money(p.profit_usd)}</strong><span>{percent(p.return_percent)}</span>{p.reason && <small>{p.reason}</small>}</div>)}</div>
      <details><summary>Meses e anos encerrados</summary><div className="portfolio-periods">{data?.periods.slice(3).map(p => <div key={p.label}><strong>{p.label}</strong><span>{money(p.profit_usd)}</span><span>{percent(p.return_percent)}</span>{p.reason && <small>{p.reason}</small>}</div>)}</div></details>
      <small>{data?.methodology}</small><small>Calculado em {data && new Date(data.generated_at).toLocaleString('pt-BR')}. Resultados dependem do histórico cadastrado.</small>
    </>}
  </div>;
}

export function PortfolioHoldingEditor({ symbol, currency, account, canManage }: { symbol: string; currency: string; account: Controller; canManage: boolean }) {
  const position = account.data?.summary?.positions[symbol];
  const [quantity, setQuantity] = useState('');
  const [total, setTotal] = useState('');
  const [day, setDay] = useState(today);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const requestId = useRef<string | null>(null);
  useEffect(() => { if (!dirty) { setQuantity(position?.quantity ?? ''); setTotal(position?.total_cost ?? ''); } }, [position?.quantity, position?.total_cost, dirty]);
  const edit = () => { setDirty(true); requestId.current = null; setMessage(''); };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); if (!canManage || busy) return; setBusy(true); setMessage('');
    try {
      requestId.current ??= crypto.randomUUID();
      await account.save({ symbol, kind: 'position', quantity: numeric(quantity), total: numeric(total), fees: '0', effective_date: day, request_id: requestId.current });
      setDirty(false); requestId.current = null; setMessage('Posição salva.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Falha ao salvar.'); } finally { setBusy(false); }
  };
  return <div className="portfolio-holding">
    {canManage && <form onSubmit={submit}>
      <label>Quantidade<input aria-label={`Quantidade de ${symbol}`} inputMode="decimal" value={quantity} onChange={e => { setQuantity(e.target.value); edit(); }} required disabled={busy} /></label>
      <label>Custo total ({currency})<input aria-label={`Custo total de ${symbol}`} inputMode="decimal" value={total} onChange={e => { setTotal(e.target.value); edit(); }} required disabled={busy} /></label>
      <label>Posição nesta data<input type="date" min="2000-01-01" max={today()} value={day} onChange={e => { setDay(e.target.value); edit(); }} required disabled={busy} /></label>
      <button type="submit" disabled={busy || !dirty}>{busy ? 'Salvando…' : 'Salvar posição'}</button>
    </form>}
    {message && <small role="status">{message}</small>}
    {position && <div className="portfolio-holding-values"><span>Valor: <strong>{money(position.value, currency)}</strong></span><span>Lucro / prejuízo em aberto: <strong>{money(position.profit, currency)} · {percent(position.profit_percent)}</strong></span><span>Realizado em vendas: {money(position.realized, currency)}</span></div>}
    {canManage && <small>Para reconstruir períodos anteriores, cadastre as compras e vendas no histórico abaixo. Salvar posição registra um saldo, não uma compra.</small>}
  </div>;
}

export function PortfolioHistory({ account, symbols, canManage }: { account: Controller; symbols: string[]; canManage: boolean }) {
  const [symbol, setSymbol] = useState('');
  const [kind, setKind] = useState('buy');
  const [day, setDay] = useState(today);
  const [quantity, setQuantity] = useState('');
  const [total, setTotal] = useState('');
  const [fees, setFees] = useState('0');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const requestId = useRef<string | null>(null);
  const changed = () => { requestId.current = null; setMessage(''); };
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); if (!canManage || busy) return; setBusy(true);
    try {
      requestId.current ??= crypto.randomUUID();
      await account.save({ request_id: requestId.current, symbol, kind, effective_date: day, quantity: kind==='dividend' ? '0' : numeric(quantity), total: kind==='split' ? '0' : numeric(total), fees: kind==='split' ? '0' : numeric(fees) });
      requestId.current = null; setMessage('Movimentação salva.'); setQuantity(''); setTotal('');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Falha ao salvar'); } finally { setBusy(false); }
  };
  return <details className="portfolio-account-history"><summary>Compras, vendas e histórico da carteira</summary>
    <p>Cadastre em ordem cronológica. Valores na moeda da ação; total da negociação antes das taxas. Desdobramento usa um fator (2 para 2:1; 0,1 para grupamento 1:10). Inclua proventos e eventos societários para um resultado completo.</p>
    {canManage && <form onSubmit={save} onChange={changed}>
      <label>Ativo<select value={symbol} onChange={e => setSymbol(e.target.value)} required disabled={busy}><option value="">Selecione</option>{symbols.map(s=><option key={s}>{s}</option>)}</select></label>
      <label>Movimentação<select value={kind} onChange={e => setKind(e.target.value)} disabled={busy}>{Object.entries(kinds).filter(([k])=>k!=='position').map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
      <label>Data<input type="date" min="2000-01-01" max={today()} required value={day} onChange={e=>setDay(e.target.value)} disabled={busy}/></label>
      {kind!=='dividend' && <label>{kind==='split'?'Fator':'Quantidade'}<input inputMode="decimal" value={quantity} onChange={e=>setQuantity(e.target.value)} required disabled={busy}/></label>}
      {kind!=='split' && <><label>Valor total<input inputMode="decimal" value={total} onChange={e=>setTotal(e.target.value)} required disabled={busy}/></label><label>Taxas<input inputMode="decimal" value={fees} onChange={e=>setFees(e.target.value)} required disabled={busy}/></label></>}
      <button disabled={busy}>{busy?'Salvando…':'Registrar'}</button>
    </form>}
    {message && <p role="status">{message}</p>}
    <div className="portfolio-ledger">{account.data?.events.slice().reverse().map(e=><div key={e.request_id}><span>{e.effective_date} · {e.symbol}</span><span>{kinds[e.kind]} · {e.quantity}</span><span>{money(e.total,e.market==='B3'?'BRL':'USD')} · taxas {money(e.fees,e.market==='B3'?'BRL':'USD')}</span>{canManage && <button disabled={busy} onClick={async()=>{setBusy(true);try {await account.cancel(e.request_id);setMessage('Registro cancelado; histórico recalculado.');}catch(error){setMessage(error instanceof Error?error.message:'Falha ao cancelar');}finally{setBusy(false);}}}>Cancelar registro</button>}</div>)}</div>
  </details>;
}
