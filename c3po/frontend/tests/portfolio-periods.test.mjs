import test from 'node:test';
import assert from 'node:assert/strict';
import { portfolioChartPeriods, monthlyResultCounts } from '../lib/portfolio-periods.ts';
const p = (label, start, profit_usd) => ({ label, start, end: start, profit_usd, reason: null });
test('chronological months; exclude overlapping summaries from quarters', () => {
 const s=portfolioChartPeriods([p('Ano em andamento','2026-01-01','999'),p('Mês em andamento','2026-03-01','30'),p('02/2026','2026-02-01','-20'),p('Hoje','2026-03-12','99'),p('01/2026','2026-01-01','10')]);
 assert.deepEqual(s.monthly.map(r=>r.label),['01/26','02/26','03/26']);
 assert.equal(s.quarterly[0].value,20); assert.equal(s.quarterly[0].label,'1Q26'); assert.equal(s.quarterly[0].partial,true); assert.equal(s.yearly[0].value,999);
});
test('missing month or null is unavailable, not zero', () => {
 for(const rows of [[p('02/2022','2022-02-01','5')],[p('01/2022','2022-01-01','1'),p('02/2022','2022-02-01',null),p('03/2022','2022-03-01','2')]]) assert.equal(portfolioChartPeriods(rows).quarterly[0].value,null);
});
test('current quarter requires elapsed months only and preserves zero', () => {
 const s=portfolioChartPeriods([p('Mês em andamento','2026-04-01','0')]); assert.equal(s.quarterly[0].value,0); assert.equal(s.quarterly[0].label,'2Q26');
});
test('year rollover, negative quarter and nonfinite rejection', () => {
 const s=portfolioChartPeriods([p('10/2022','2022-10-01','-5'),p('11/2022','2022-11-01','-10'),p('12/2022','2022-12-01','2'),p('2022','2022-01-01','-13'),p('Mês em andamento','2023-01-01','Infinity')]);
 assert.deepEqual(s.quarterly.map(r=>[r.label,r.value]),[['4Q22',-13],['1Q23',null]]); assert.equal(s.yearly[0].value,-13);
});

test('two-digit years in monthly and annual chart labels', () => {
 const s=portfolioChartPeriods([p('12/2022','2022-12-01','1'),p('2022','2022-01-01','1')]);
 assert.equal(s.monthly[0].label,'12/22'); assert.equal(s.yearly[0].label,'22');
});
test('monthly counters include current month and separate zero and unavailable', () => {
 const s=portfolioChartPeriods([p('01/2026','2026-01-01','10'),p('02/2026','2026-02-01','-5'),p('03/2026','2026-03-01','0'),p('04/2026','2026-04-01',null),p('Mês em andamento','2026-05-01','3'),p('Ano em andamento','2026-01-01','8')]);
 assert.deepEqual(monthlyResultCounts(s.monthly),{positive:2,negative:1,zero:1,unavailable:1});
 assert.deepEqual(monthlyResultCounts([]),{positive:0,negative:0,zero:0,unavailable:0});
});
