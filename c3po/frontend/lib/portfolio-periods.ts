export type PortfolioPeriod = { label: string; start: string; end: string; profit_usd: string | null; reason: string | null };
export type ChartPeriod = { label: string; value: number | null; partial: boolean; reason: string | null };
const valueOf = (p: PortfolioPeriod) => p.profit_usd == null || !p.profit_usd.trim() || !Number.isFinite(Number(p.profit_usd)) ? null : Number(p.profit_usd);

// Only monthly periods are added together; annual/current summary rows overlap them.
export function portfolioChartPeriods(periods: PortfolioPeriod[]) {
  const months = periods.filter(p => /^\d{2}\/\d{4}$/.test(p.label) || p.label === 'Mês em andamento')
    .slice().sort((a, b) => a.start.localeCompare(b.start));
  const monthly: ChartPeriod[] = months.map(p => ({ label: `${p.start.slice(5, 7)}/${p.start.slice(2, 4)}`, value: valueOf(p), partial: p.label === 'Mês em andamento', reason: p.reason }));
  const groups = new Map<string, PortfolioPeriod[]>();
  for (const p of months) {
    const key = `${p.start.slice(0, 4)}-${Math.floor((Number(p.start.slice(5, 7)) - 1) / 3) + 1}`;
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  const quarterly: ChartPeriod[] = [...groups].map(([key, rows]) => {
    const [year, q] = key.split('-');
    const partial = rows.some(p => p.label === 'Mês em andamento');
    const count = partial ? (Number(rows[rows.length - 1].start.slice(5, 7)) - 1) % 3 + 1 : 3;
    const expected = Array.from({ length: count }, (_, i) => `${year}-${String((Number(q) - 1) * 3 + i + 1).padStart(2, '0')}-01`);
    const complete = rows.length === count && expected.every(start => rows.some(p => p.start === start && valueOf(p) !== null));
    return { label: `${q}Q${year.slice(2)}`, partial, value: complete ? rows.reduce((sum, p) => sum + valueOf(p)!, 0) : null, reason: complete ? null : 'Histórico mensal incompleto neste trimestre.' };
  });
  const yearly: ChartPeriod[] = periods.filter(p => /^\d{4}$/.test(p.label) || p.label === 'Ano em andamento')
    .slice().sort((a, b) => a.start.localeCompare(b.start))
    .map(p => ({ label: p.start.slice(2, 4), value: valueOf(p), partial: p.label === 'Ano em andamento', reason: p.reason }));
  return { monthly, quarterly, yearly };
}

export function monthlyResultCounts(rows: ChartPeriod[]) {
  return rows.reduce((counts, row) => {
    if (row.value === null || !Number.isFinite(row.value)) counts.unavailable++;
    else if (row.value > 0) counts.positive++;
    else if (row.value < 0) counts.negative++;
    else counts.zero++;
    return counts;
  }, { positive: 0, negative: 0, zero: 0, unavailable: 0 });
}
