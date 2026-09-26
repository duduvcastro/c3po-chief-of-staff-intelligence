"use client";

import { useState } from "react";
import { portfolioChartPeriods, type PortfolioPeriod, type ChartPeriod } from '../lib/portfolio-periods';
import styles from './portfolio-period-charts.module.css';

const usd = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD' }).format(value);

function PeriodChart({ title, rows: allRows, limit }: { title: string; rows: ChartPeriod[]; limit?: number }) {
  const [showAll, setShowAll] = useState(false);
  const rows = showAll || !limit ? allRows : allRows.slice(-limit);
  const max = Math.max(1, ...rows.map(row => Math.abs(row.value ?? 0)));
  const width = Math.max(640, rows.length * 148 + 40);
  const slot = (width - 40) / Math.max(1, rows.length);
  const zero = 150;
  return <section className={styles.chart} aria-label={title}>
    <div className={styles.header}><h3>{title}</h3>{limit && allRows.length > limit && <button type="button" aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>{showAll ? "Ver recentes" : "Ver tudo"}</button>}</div>
    {!rows.length ? <p>Ainda não há registros para este gráfico.</p> : <div className={styles.scroll} tabIndex={0} role="region" aria-label={`${title}: role horizontalmente para ver todo o histórico`}>
      <svg width={width} height={320} role="img" aria-label={`${title}, resultados em dólares. Valores positivos em verde e negativos em vermelho.`}>
        <title>{`${title} · USD`}</title>
        <line x1={20} x2={width - 20} y1={zero} y2={zero} stroke="currentColor" opacity={0.5} />
        <text x={4} y={zero - 6} className={styles.zero}>0</text>
        {rows.map((row, i) => {
          const x = 20 + slot * (i + 0.5);
          const height = Math.abs(row.value ?? 0) / max * 102;
          const negative = row.value !== null && row.value < 0;
          const y = negative ? zero : zero - height;
          const label = row.value === null ? 'N/D' : usd(row.value);
          return <g key={row.label}>
            <title>{`${row.label}${row.partial ? " (em andamento)" : ""}: ${label}${row.reason ? ` — ${row.reason}` : ""}`}</title>
            {row.value !== null && row.value !== 0 && <rect x={x - 26} y={y} width={52} height={height} rx={3} fill={negative ? '#b42318' : '#087f5b'} />}
            <text x={x} y={negative ? zero + height + 19 : zero - height - 10} textAnchor="middle" className={styles.value}>{label}</text>
            <text x={x} y={292} textAnchor="middle" className={styles.period}>{row.label}</text>
            {row.partial && <text x={x} y={310} textAnchor="middle" className={styles.partial}>Em andamento</text>}
          </g>;
        })}
      </svg>
    </div>}
  </section>;
}

export function PortfolioPeriodCharts({ periods }: { periods: PortfolioPeriod[] }) {
  const series = portfolioChartPeriods(periods);
  return <div className={styles.charts}>
    <p className={styles.caption}>Resultados em USD · Verde: lucro · Vermelho: prejuízo. Períodos em andamento incluem os dados disponíveis até hoje; N/D indica histórico insuficiente.</p>
    <PeriodChart title="Resultado mês a mês" rows={series.monthly} limit={24} />
    <PeriodChart title="Resultado por trimestre" rows={series.quarterly} limit={12} />
    <PeriodChart title="Resultado ano a ano" rows={series.yearly} />
  </div>;
}
