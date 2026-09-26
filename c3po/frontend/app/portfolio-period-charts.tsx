"use client";

import { useEffect, useRef, useState } from "react";
import { portfolioChartPeriods, type PortfolioPeriod, type ChartPeriod } from '../lib/portfolio-periods';
import styles from './portfolio-period-charts.module.css';

const usd = (value: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'USD' }).format(value);

function PeriodChart({ title, rows }: { title: string; rows: ChartPeriod[] }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<number | null>(null);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(1, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const max = Math.max(1, ...rows.map(row => Math.abs(row.value ?? 0)));
  const slot = Math.max(1, width - 48) / Math.max(1, rows.length);
  const barWidth = Math.min(52, slot * 0.72);
  const stride = Math.max(1, Math.ceil(76 / slot));
  const zero = 150;
  const describe = (row: ChartPeriod) => `${row.label}${row.partial ? ' (em andamento)' : ''}: ${row.value === null ? 'N/D' : usd(row.value)}${row.reason ? ` — ${row.reason}` : ''}`;
  const selected = active === null ? null : rows[active];
  return <section className={styles.chart} aria-label={title}>
    <h3>{title}</h3>
    {!rows.length && <p>Ainda não há registros para este gráfico.</p>}
    <div className={styles.plot} ref={container}>
      {!!rows.length && <svg width="100%" height={320} viewBox={`0 0 ${width} 320`} role="group" aria-label={`${title}, resultados em dólares. Todo o histórico; verde positivo e vermelho negativo.`}>
        <title>{`${title} · USD`}</title>
        <line x1={24} x2={width - 24} y1={zero} y2={zero} stroke="currentColor" opacity={0.5} />
        <text x={4} y={zero - 6} className={styles.zero}>0</text>
        {rows.map((row, i) => {
          const x = 24 + slot * (i + 0.5);
          const height = Math.abs(row.value ?? 0) / max * 102;
          const negative = row.value !== null && row.value < 0;
          const label = row.value === null ? 'N/D' : usd(row.value);
          const tick = i === 0 || i === rows.length - 1 || (i % stride === 0 && i < rows.length - stride);
          return <g key={row.label} tabIndex={0} role="button" aria-label={describe(row)} onFocus={() => setActive(i)} onMouseEnter={() => setActive(i)} onClick={() => setActive(i)} onKeyDown={event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setActive(i); }
          }} className={styles.bar}>
            <title>{describe(row)}</title>
            <rect x={x - slot / 2} y={30} width={slot} height={245} fill="transparent" />
            {row.value !== null && row.value !== 0 && <rect x={x - barWidth / 2} y={negative ? zero : zero - height} width={barWidth} height={height} rx={Math.min(3, barWidth / 4)} fill={negative ? '#b42318' : '#087f5b'} />}
            {row.value === null && <circle cx={x} cy={zero} r={Math.min(2, slot / 3)} fill="currentColor" opacity={0.5} />}
            {slot >= 140 && <text x={x} y={negative ? zero + height + 19 : zero - height - 10} textAnchor="middle" className={styles.value}>{label}</text>}
            {tick && <text x={x} y={292} textAnchor={i === 0 ? 'start' : i === rows.length - 1 ? 'end' : 'middle'} className={styles.period}>{row.label}</text>}
            {row.partial && <text x={x} y={310} textAnchor="end" className={styles.partial}>Em andamento</text>}
          </g>;
        })}
      </svg>}
    </div>
    <p className={styles.detail} aria-live="polite">{selected ? describe(selected) : 'Passe o mouse, toque ou use Tab nas barras para consultar o período e o valor.'}</p>
  </section>;
}

export function PortfolioPeriodCharts({ periods }: { periods: PortfolioPeriod[] }) {
  const series = portfolioChartPeriods(periods);
  return <div className={styles.charts}>
    <p className={styles.caption}>Todo o histórico desde o primeiro investimento · Resultados em USD · Verde: lucro · Vermelho: prejuízo. Períodos em andamento incluem os dados disponíveis até hoje; N/D indica histórico insuficiente.</p>
    <PeriodChart title="Resultado mês a mês" rows={series.monthly} />
    <PeriodChart title="Resultado por trimestre" rows={series.quarterly} />
    <PeriodChart title="Resultado ano a ano" rows={series.yearly} />
  </div>;
}
