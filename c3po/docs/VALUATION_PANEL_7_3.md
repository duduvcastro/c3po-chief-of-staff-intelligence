# Valuation V3.2 — painel semanal de medição (§7.3), implementação v1

Referência normativa: spec V3.2 rev 7 (congelada a três, `d31ed90e…`), §7.3 item 3 (gates de sanidade reclassificados; nível e dispersão; erro realizado; cobertura das bandas = **PROMO-1**; protocolo de promoção contra o consenso = **PROMO-2**; ramos de zero = **PROMO-2-ZERO**), §2.2 (dados, rótulo, três relógios, atrito por causa, `duplicate_session`) e §2.6 (log-erro, `MSE` em log², `N_EVAL`, mínimos, atrito ≤ 10 %). Módulo `c3po/backend/app/valuation_panel.py`; testes `tests/test_valuation_panel.py`; leitor novo `Database.list_valuation_predictions_in_window`.

## O que é

- **Medição, nunca gate.** O painel lê o armazenamento persistido e publica números. Não bloqueia rodada, não muda nada do que é servido (seleção oficial, screeners, One Pager, R2D2), não escreve no banco. As travas do §7-bis (`consumer_change_authorized`, `official_tp_replacement_authorized`) não são lidas nem tocadas.
- **Insumos (só o store; zero rede).**
  1. Registros de previsão imutáveis `valuation_predictions`, por `(fonte, versão da fonte)` — hoje só `official_blend_v1` (versão da metodologia, ex. `"7"`); as fontes `v3_shadow`/`v3_2_shadow` existem como conceito e o painel as aceita pelo nome, mas **não têm emissor** em `valuation_predictions` ainda (limitação declarada abaixo). Campos usados: `tp`, `price`, `currency`, `session_date` (já é a última sessão concluída do calendário do mercado), `prediction_instant`, `published_at` (= `available_at` do registro), `bear_tp`/`bull_tp`, `decomposition.consensus{tp, source, horizon, currency, published_at, payload_sha256}` e `decomposition.provenance.rerun_of`.
  2. Série de preços persistida `valuation_price_history/<M>` lida **sempre** através de `PriceHistoryService.bars/label_bar/vintage` com `available_before = C` (o corte): uma única safra por mercado e corte (maior `available_at < C`), `close` e `adjusted_close` da mesma safra, três relógios.
  3. Calendários `exchange_calendars` (versão gravada no recibo): `BVMF` para B3, `XNYS` para NASDAQ/NYSE — os mesmos mapas de `valuation_official` e `valuation_price_history`.
- **Consenso factual (PROMO-2 c).** Sempre o bloco persistido no próprio registro (`decomposition.consensus`), com fonte, horizonte declarado, moeda, instante (`published_at`) e hash. Nunca se relê o consenso atual. O bloco só é `present` (entra na máscara comum e no nível/dispersão) quando está **atestado** — moeda, `published_at` e `payload_sha256` presentes, instante legível — e o seu `published_at ≤ prediction_instant` (o consenso que **existia** no instante da previsão). Causas de exclusão, todas contadas em `common_mask.excluded` e `level_dispersion.<perfil>.consensus_excluded`: `absent` (sem `tp`); `consensus_unattested` (sem bloco, ou bloco sem moeda/instante/hash, ou instante ilegível — a coluna plana `consensus_tp` de um registro sem bloco é reportada como `tp` mas não atesta nada); `consensus_after_prediction` (`published_at` do bloco **posterior** ao `prediction_instant`: o bloco de um re-run, nunca o consenso que existia); `consensus_currency_mismatch` (moeda do bloco ≠ moeda do registro).
- **Relógio.** O corte `C` é obrigatório e com fuso (`--as-of`; um instante ingénuo é recusado). Nada lê `now()`. O recibo é função determinística de `(C, store)` **enquanto `C` estiver dentro do horizonte do calendário** (ver "`beyond_calendar`" nas limitações): `cut_within_calendar_horizon` na célula diz se está.

## Semântica

**Admissibilidade (§2.2, PROMO-2 b).** Um registro entra se `prediction_instant ∈ [since, until)` (janela opcional, `outside_window`), `published_at < C` (`published_at_not_before_cut`; registro sem `published_at` — linha V1 legada — é `no_published_at`: dado sem `available_at` é inelegível), `tp > 0` (`tp_not_positive`), sessão parseável (`session_unparseable`) **e sessão do calendário do mercado do registro** (`session_not_in_calendar`: fim de semana, feriado, data fora dos limites do calendário ou mercado desconhecido — recusado aqui, nunca vira observação; o denominador decide-se antes); e **uma só observação por `(fonte, símbolo, sessão)`, qualquer que seja a versão da fonte**: entra o registro de **menor `published_at`** (o primeiro que existiu), os demais — outra versão da mesma fonte, re-run, segundo ciclo da mesma sessão — são `duplicate_session` (contados, nunca somados). Desempate determinístico por `(published_at, prediction_instant, símbolo, cycle_id)`. Re-runs (`rerun_of` não nulo) são admissíveis quando `published_at < C` e não há registro anterior da mesma `(fonte, símbolo, sessão)`; são **contados** (`records.reruns`). A regra "`available_at − prediction_instant ≤ 1 sessão` para valer como previsão" (§2.2 R3 a) fica **declarada e não aplicada nesta v1** — decisão a confirmar pela mesa; o painel só recusa `published_at ≥ C` e publica a contagem de re-runs.

**Rótulo (§2.2, convenção `total_return:adjusted_close`).** Para `(i, T)` e horizonte `h` em sessões:

```text
a(T)          = adjusted_close(T) / close(T)             # barra em T, da MESMA safra S do corte
P_real(T,h)   = adjusted_close(T + h)                     # T + h em sessões do calendário do mercado
e_fonte       = ln( tp · a(T) ) − ln( P_real )
e_consenso    = ln( consensus_tp · a(T) ) − ln( P_real )  # só quando o consenso persistido está `present` (atestado, anterior ou igual ao instante da previsão, na moeda do registro)
```

Verificação de base por `(i, T)`, nesta ordem: moeda da barra em `T` ≠ moeda do registro (ambas presentes) → `label_unavailable:currency_mismatch` (§2.2: preço noutra moeda não é base para o TP, seja qual for a tolerância); sem `price` no registro → `label_unavailable:basis_unverifiable`; `|price − close(T)| / close(T) > TOL_BASIS = 0,02` → `label_unavailable:basis_mismatch`; sem barra em `T` na safra → `label_unavailable:adjustment_unknown`. Cobertura das bandas: `bear_tp ≤ P_real / a(T) ≤ bull_tp` (o preço realizado na base de `T`).

**Denominador e atrito.** Elegível = `(i, T)` cuja sessão `T + h` **fechou antes de `C`** (fecho do calendário; um corte exatamente no fecho não é maduro). `not_yet_mature` e `beyond_calendar` são as **únicas** causas fora do denominador, contadas à parte (`ineligible`); uma sessão `T` que não é sessão do calendário nunca chega aqui (recusada na admissibilidade). Atrito = `label_unavailable / elegíveis`, publicado por causa: `no_vintage`, `manifest_mismatch`, `symbol_not_in_vintage`, `vintage_unreproducible`, `bar_hash_mismatch`, `vintage_mismatch`, `outside_window`, `missing_bar`, `label_unavailable:adjustment_unknown`, `label_unavailable:basis_mismatch`, `label_unavailable:basis_unverifiable`, `label_unavailable:currency_mismatch`. Uma barra indisponível no corte é rótulo ausente — nunca um preço de outra fonte.

**Métricas por mercado, fonte e horizonte** (`horizons."21"|"42"|"63"|"126"`): `eligible`, `ineligible`, `labelled`, `attrition{rate, unavailable, by_cause}`, `source{n, mse, median_abs_log_error, mean_log_error}` sobre todas as observações rotuladas, `consensus{…}` e `source_on_common_mask{…}` sobre a **máscara comum** (fonte, consenso e rótulo presentes), `common_mask{n, names, sessions, max_share_single_name, excluded{absent, consensus_unattested, consensus_after_prediction, consensus_currency_mismatch}}`, `band_coverage{n_with_bands, n_null_bands, within, fraction}` (bandas nulas excluídas e contadas). `MSE` é em log², nunca em p.p. Somas em ordem fixa `(símbolo, sessão)`; `-0.0` normalizado.

**Decisão pré-registrada (PROMO-2 e, PROMO-2-ZERO), só em `h = 126`**, na ordem: atrito `> 0,10` (ou nenhuma observação elegível) → `UNMEASURED` **antes de qualquer contagem**; mínimos **após a interseção** — `n ≥ N_EVAL = 30`, `≥ 10` nomes, `≥ 10` sessões — senão `INSUFFICIENT` (razões listadas); `MSE_consenso = 0` e `MSE_fonte = 0` → `TIE` (satisfaz a desigualdade, conta como aprovado, marcador `tie = true`, razão `N/D`); `MSE_consenso = 0` e `MSE_fonte > 0` → `FAIL`, razão `N/D`; caso contrário razão `MSE_fonte / MSE_consenso` reportada, `PASS` sse `MSE_fonte ≤ 1,00 × MSE_consenso`, com `passes_k_1_05` reportado ao lado. Sem epsilon, sem escolha de política depois do resultado. `21/42/63` são `diagnostic_only = true`; `consensus_declared_horizon` (252 sessões) publica só o lado do consenso. A combinação dos três mercados (`k = 1,00` em pelo menos dois e `1,05` no terceiro, §10.9) sai em `combination.<fonte>` e é `NOT_EVALUABLE` enquanto faltar mercado ou algum estiver `UNMEASURED`/`INSUFFICIENT`.

**Nível e dispersão vs consenso no instante da previsão** (`level_dispersion.<perfil>`; perfil = `source_version` do registro ou `--profile-label`): `median_level` = mediana de `tp / consenso − 1`; `centred_quantiles` p10/p25/p75/p90 dos desvios centrados (desvio − mediana); `sanity{p50_abs, p90_abs, status}` sobre `|tp / consenso − 1|` com `SANITY_OK` sse p50 ≤ 15 % e p90 ≤ 30 %, `SANITY_OUT` senão, `SANITY_UNMEASURED` sem amostra — **`blocking: false` sempre** (§7.3 rev 5: uma falha exige justificativa lavrada da mesa com o erro realizado dos dois lados; não bloqueia por si). Quantis por interpolação linear (a mesma convenção de `valuation_v3_shadow._percentile`, copiada e pinada por teste).

## Constantes pré-registradas (todas dentro do payload hasheado)

`SCHEMA_VERSION = VALUATION-PANEL-7-3-v1`; `HORIZONS = (21, 42, 63, 126)`; `DECISORY_HORIZON = 126`; `CONSENSUS_DECLARED_HORIZON = 252`; `K_PRIMARY = 1,00`; `K_SECONDARY = 1,05`; `N_EVAL = 30`; `MIN_NAMES = 10`; `MIN_SESSIONS = 10`; `ATTRITION_CAP = 0,10`; `SANITY_P50 = 0,15`; `SANITY_P90 = 0,30`; `TOL_BASIS = 0,02`; `QUANTILES = (0,10, 0,25, 0,75, 0,90)`; `LABEL_CONVENTION = total_return:adjusted_close`; calendário `{BVMF, XNYS}` + versão do `exchange_calendars`.

## Recibo

```text
{ "schema": "VALUATION-PANEL-7-3-v1",
  "payload": { "schema", "protocol": {constantes acima, "gate": false}, "cut", "window": {since, until, profile_label},
               "markets": [...], "sources": [...],
               "results": { <M>: { <fonte>: {
                   "records": {read, admissible, refused: {causa: n}, reruns},
                   "observations": {n, names, sessions, max_share_single_name, basis: {ok|label_unavailable:…: n}},
                   "vintage": {status, publication_id, price_snapshot_id, available_at, fetched_at, window},   # a safra do corte, ou nulos
                   "last_closed_session", "cut_within_calendar_horizon": true|false, "horizons": {"21": …, "42": …, "63": …, "126": …},
                   "decision": {status, ratio, passes_k_1_00, passes_k_1_05, tie, reasons, n, names, sessions, attrition, mse_source, mse_consensus, k_primary, k_secondary},
                   "consensus_declared_horizon": {…, "consensus_only": true},
                   "level_dispersion": { <perfil>: {n, consensus_excluded, median_level, centred_quantiles, sanity} } } } },
               "combination": { <fonte>: {status: PASS|FAIL|NOT_EVALUABLE, markets_missing, markets_unmeasured, passed_k_1_00, passed_k_1_05, ties, gate: false} } },
  "payload_sha256": sha256 canónico do payload (sort_keys, separadores compactos) }
```

O payload **não contém símbolo, `cycle_id` nem `row_sha256`** (teste varre o JSON pelos nomes da fixture) nem `built_at`: reconstruí-lo depois com o mesmo store e o mesmo corte reproduz o hash (teste de permutação do store; teste com o limite do calendário recuado — o mesmo hash enquanto `C` está dentro do calendário). O detalhe por `(i, T)` — com símbolo, `cycle_id`, `row_sha256`, `a(T)`, `close(T)`, e por horizonte a sessão-alvo, `realized`, `bar_sha256`, `e_source`, `e_consensus`, `within_bands` — só sai por `--detail`, num caminho **novo**, com `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` e modo `0600` (caminho existente ou symlink, pendente incluído → recusado, nada escrito).

## CLI

```text
python -m app.valuation_panel --as-of 2026-09-14T00:00:00-03:00 [--markets B3,NASDAQ,NYSE] [--sources official_blend_v1[,v3_2_shadow]]
                              [--since ISO-com-fuso] [--until ISO-com-fuso] [--profile-label X] [--detail /caminho/novo.json]
```

stdout = o recibo (`json.dumps(sort_keys=True)`), sem símbolos; código de saída `0` sempre que mediu (`UNMEASURED`/`INSUFFICIENT` não são erro); `2` (parser) para `--as-of`/`--since`/`--until` ingénuos ou ilegíveis, mercado desconhecido, lista de fontes vazia, `--since ≥ --until`, `--detail` existente/symlink — nesses casos nada é impresso. O serviço constrói o seu próprio `PriceHistoryService` sobre um cliente HTTP que **levanta em qualquer chamada** (`_NoNetworkHttp`, contador pinado a zero) e sobre um proxy `_CutReads` que memoiza, durante a corrida, as duas leituras de safra que `label_bar` faz por chamada (`latest_analysis_snapshot_before`, `analysis_snapshot_by_id`) — exato porque o corte é constante e o store é append-only; uma publicação que chegasse a meio de uma corrida com corte no futuro seria vista pela corrida inteira ou por nenhuma parte dela.

## Limitações declaradas

- **Maturidade.** `h = 126` sessões ≈ 6 meses: para registros de agosto/setembro de 2026 tudo é `not_yet_mature` até ~março de 2027 (fora do denominador, nunca atrito). Até lá a decisão é `UNMEASURED` (`no_eligible_observations`) por construção — declarado, não contornado.
- **Série dormente.** `valuation_price_history_enabled = False` e backfill sob ordem do dono: sem safra publicada antes do corte, todo rótulo maduro é `no_vintage` (atrito 100 %, `UNMEASURED`) e `vintage.status = null` no recibo.
- **Fontes sem emissor.** `v3_shadow`/`v3_2_shadow` não gravam em `valuation_predictions`; pedi-las dá uma célula vazia declarada (`records.read = 0`, `UNMEASURED`). A desigualdade V3.2 × consenso não é avaliável hoje. Para `official_blend_v1` o TP **contém** o consenso (blend), logo o nível/dispersão vs consenso não é a leitura do TP interno do §7.3 — rotulado por fonte, nunca misturado.
- **Verificação de base.** `TOL_BASIS` compara o `price` do registro (spot intradia do universo) com o `close(T)`; pode inflar o atrito — publicado por causa, para a mesa decidir.
- **`beyond_calendar` e o relógio de parede.** `exchange_calendars` constrói o calendário até **hoje + 1 ano** — um limite que depende do dia em que o painel corre, não do store. Uma sessão-alvo `T + h` além desse limite vem de `label_bar` como `beyond_calendar`; o painel (`resolve_label`, só no painel — `valuation_price_history` não é tocado) reclassifica-a **deterministicamente** como `not_yet_mature` quando o fecho da **última sessão do calendário é ≥ `C`** (a sessão-alvo, ainda mais tarde, não fechou antes de `C`: exatamente o que um calendário mais longo responderia). Quando o próprio `C` está além do calendário (fecho da última sessão `< C`, ou calendário indisponível) o alvo pode ou não ter maturado — `beyond_calendar` fica (inelegível, contado à parte) e o recibo **deixa de ser** função de `(C, store)` apenas: a célula publica `cut_within_calendar_horizon = false`. Regra prática: correr o painel com `C` ≤ hoje + 1 ano (o caso normal, `C` ≈ agora) garante o mesmo `payload_sha256` em qualquer dia.
- **`valuation_accuracy`** grada em dias civis com `now()` e métricas em p.p.: reaproveitado só na forma (registros por fonte), não como motor.
