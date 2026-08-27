# MICROSTRUCTURE_TAPE_PROBE_V1 — segunda fonte de tape com sale conditions (Fase 1)

**Data:** 27/08/2026 · **Autor da spec:** Fable · **Status:** aguarda três assinaturas ANTES de
qualquer conta ser criada ou dado ser comprado.

## 1. Pergunta pré-registrada

As classes `tolerance_band` e `violation` dos gates (EMENDA 1 / Atestação 2) têm hoje uma
explicação **plausível e não provada**: trades reais com condições especiais (odd lots,
derivatively-priced, late reports) aparecem no stream de trade ticks mas **não atualizam** o
high/low oficial das barras de minuto. Este probe compra o tape com condições e transforma a
hipótese em medição.

Evidência motivadora (hasheada): probe residual do estudo de saída `864b494e…c124c`
(93 não explicados por relógio; mediana 6,34 bps; 87% coerentes com o lado da estratégia) e
report final do dry-run de entrada (relay `9e98e7998e6e2aaa…`, self-hash `23ede14e…`):
296 contained / 32 clock_extended / **85 tolerance_band** / 10 bar_unavailable / **3 violation**
(PNRG 41,1 · BVN 41,5 · DXST 34,3 bps).

## 2. Escopo da Fase 1 — um probe, uma vez

- **Fonte:** Databento (histórico, pay-as-you-go), dataset de trades consolidados de US equities
  **com sale conditions**. Racional vs. Polygon: sem assinatura mensal para uso único; Polygon só
  entra por adendo assinado se o Databento falhar no escopo.
- **Amostra (determinística, sem escolha humana):** o probe re-deriva, dos MESMOS insumos
  congelados e com o MESMO classificador importado dos gates, a lista de fills classificados
  `clock_extended`, `tolerance_band` e `violation` nos dois estudos (re-run de saída de 27/08
  00:15 e dry-run final de entrada), deduplicada por (símbolo, sessão, janela). Estimativa:
  ~150–250 janelas de ±5 minutos.
- **Classificação pré-registrada por caso** (exclusiva, nesta ordem):
  1. `condition_explained` — existe trade real no tape a ≤2 bps do signal_price dentro da janela,
     com condição que NÃO atualiza high/low oficial;
  2. `aggregation_diff` — existe trade real a ≤2 bps com condição normal (divergência de
     consolidação entre provedores);
  3. `no_tape_support` — nenhum trade a ≤10 bps do signal_price na janela: o tick persistido não
     tem suporte no tape (alimenta o workstream provider_ts/staleness);
  4. `inconclusive` — dados do provedor ausentes/insuficientes para a janela, contado.
- **Leitura pré-registrada:** apenas proporções com contagens por classe, por estudo e por
  sessão. Interpretação forte exige (1)+(2) ≥ 70% dos casos amostrados com ≤10% `inconclusive`.
  NENHUMA mudança de gate, tolerância ou spec decorre deste probe — qualquer consequência é
  emenda separada, assinada.

## 3. Orçamento e credenciais

- **Teto DURO da Fase 1: US$ 50**, com limite de gasto configurado no console do Databento
  ANTES da primeira chamada. Estouro = probe aborta e reporta parcial como parcial.
- Conta: **criada pelo Codex, por delegação expressa do Dudu** (registrada em 27/08); meio de
  pagamento fornecido pelo Dudu por canal seguro, nunca por chat. O limite de gasto de US$ 50 é
  configurado no console ANTES da primeira chamada. Chave vai para o `.env` do servidor como
  `C3PO_DATABENTO_API_KEY`; nunca em repo, nunca em log, nunca em chat.
- Estimativa honesta de custo: janelas de minutos de ~200 símbolos-sessão são MBs — esperado
  ≪ US$ 20; o teto de 50 é margem, não meta.

## 4. Execução

1. Codex implementa o probe como script standalone read-only (padrão dos probes: zero escrita em
   produção, zero mudança de estratégia), com manifest de insumos e report com self-hash;
2. Auditoria do Fable antes de rodar;
3. Uma execução no servidor; evidência bruta (tape baixado) + report hasheados no relay;
4. Mesa lê as proporções e decide, por emenda própria, se algo muda nos gates.

## 5. Fora de escopo (Fase 2, spec separada se a Fase 1 justificar)

Ingestão contínua de microestrutura, dimensão de liquidez intraday prospectiva do estudo de
entrada, escolha de provedor permanente e qualquer integração de produção.

## Assinaturas

- **Fable:** ASSINADO — 27/08/2026.
- **Codex:** pendente.
- **Dudu:** ASSINADO — 27/08/2026 ("ok" à spec, com a delegação da criação da conta ao Codex).
