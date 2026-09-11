# Valuation V3.2 — reexecutor ponto-no-tempo (`app/valuation_pit_rerun.py`), implementação v1

Referência normativa: `V3_2_RETRO_PIT_DESENHO_2026-09-11_rev2.md` (desenho rev 2, sucede a rev 1 corrigida pelo NO-GO documental do Codex #348/5638556360) sobre a base `f107858f`; ordem `DUDU_ORDER_V3_2_RETROSPECTIVA_36M_DIAGNOSTICO_2026-09-11.json` rev 1a. **Rótulo: diagnóstico.** Nada aqui é treino, gate PROMO-2, promoção ou troca de fonte oficial; a seleção oficial (`valuation_official`) continua a recusar `v3_2_shadow` (teste fixa).

## O que é

O módulo reexecuta o **`ValuationV3Engine`** (rev 7) para um instante económico `T` no passado, **pelo mesmo caminho do shadow noturno** (`valuation_v3_shadow._contexts` → `ValuationV3Engine(today = T, macro_as_of ≤ T)` → `_evaluate_market`; função `evaluate_loaded`), alimentado só com entradas **disponíveis em T "conforme evidência ou hipótese declarada"** — nunca "exatamente o que se sabia em T": o vintage original do provedor é `N/D` para toda entrada, e o registro diz isso (`provenance.availability_rule`, `price_vintage.historical_vintage = "N/D"`, `published_at_original = "N/D"`).

Os resultados são gravados como **registros de predição** (`valuation_predictions`) da fonte `v3_2_shadow` — agora um conjunto *recordable* separado (`valuation_official.RECORDABLE_SOURCES = OFFICIAL_SOURCES + ("v3_2_shadow",)`; `prediction_from_row` aceita, `_selected_source`/`_new_generation`/o escritor de seleção recusam como antes) — e como **um snapshot por corrida** (`analysis_type = valuation_pit_rerun`). Leitura: `valuation_panel --sources v3_2_shadow`, bloco `retrospective` (o painel classifica tudo `retrospective` por construção: `published_at` é o agora real, muito depois do fecho seguinte a `T`).

## Três relógios por registro (desenho §2)

| Relógio | Valor | Onde |
|---|---|---|
| `T` | data económica do cálculo | `prediction_instant`; `session_date` = última sessão fechada em `T` (`session_date_of`) |
| `published_at` | instante real da persistência (nunca retrodatado; `published_at ≥ T` conferido antes de escrever — o `CHECK` da 048 espelhado) | registro e snapshot (o mesmo instante: a identidade das linhas é determinística dada a corrida) |
| disponibilidade por entrada | `{"kind": "evidence" \| "hypothesis", "rule", "period_end", "available_at", "published_at_original": "N/D"}` | `provenance.availability_hypotheses` (lista), manifesto |

- **Demonstrações EUA**: `filing_date` do provedor = *evidência de disponibilidade do provedor* (não do regulador). Sem `filing_date` → período **não elegível** (contado em `pit_excluded_inputs`), nunca valor corrente.
- **Demonstrações B3**: o `filing_date` coincide com o fim do período → **não é evidência**; o período entra sob a **hipótese declarada `period_end+90d`** (`availability_of`). O lag é uma hipótese rotulada; **nunca é chamado de "publicação original"** (o teste confere que a regra não contém as palavras).
- **Quantidade de ações**: `commonStockSharesOutstanding` do último balanço elegível (com a disponibilidade desse balanço), senão `outstandingShares` com `period_end+90d` como hipótese (para todo mercado — o provedor data essas observações por período).
- **`--as-of` exige fuso**; um `T` ingénuo é recusado no parser e em `compute()`.

## Campos admitidos e reconstrução causal (desenho §3)

Só dois blocos do payload EODHD são lidos: `Financials.{Income_Statement,Balance_Sheet,Cash_Flow}.{quarterly,yearly}` e `outstandingShares` (`ALLOWED_PAYLOAD_BLOCKS`). `General`, `Highlights`, `Valuation`, `Technicals`, `SharesStats`, `AnalystRatings`, `Earnings`, … **nunca são lidos** — o teste com fixture envenenada (blocos correntes com valores absurdos + um mapping que explode ao toque) prova-o na função pura e de ponta a ponta (resultados idênticos aos do payload limpo).

Reconstruído por símbolo em `T` (`pit_fundamentals` + `PitSourceResolver._symbol_inputs`):

| Entrada do motor | Reconstrução |
|---|---|
| TTM (receita, lucro, EBITDA, dividendos, FCF) | soma dos 4 últimos trimestres elegíveis (span ≤ 400 d); senão o último exercício elegível (`ttm.basis` declara) |
| Balanço | último elegível (patrimônio, dívida, caixa, ações) |
| `price`, `market_cap` | fecho da última sessão ≤ sessão de `T` na safra pinada × ações em `T` |
| `eps`, `pe`, `ev_ebitda`, `book_value`, `price_to_book`, `roe`, `dividend_yield` | recalculados dos elegíveis; `forward_pe` ausente |
| `ratios_annual`, `key_metrics_annual` | por exercício elegível, com o **preço de fecho ≤ fim do exercício** (tolerância 30 d) da safra pinada; exercício sem preço/ações é excluído e contado |
| Beta | OLS dos log-retornos diários (≤ 252 sessões ≤ T) contra o **proxy equiponderado do universo** (não há série de índice persistida; método declarado em `provenance.beta`); insuficiente → ausente (o motor usa 1,0) e contado |
| Pares | nomes do **mesmo setor do catálogo** no mercado da corrida; múltiplos dos pares recalculados dos fundamentos elegíveis em T; medianas setoriais por `_sector_medians` sobre as linhas reconstruídas |
| Qualidade (V3.1) | base `chewie_trailing` recomputada (ROE TTM + crescimento de receita TTM vs. TTM anterior) via `build_quality_index`; base `fmp_forward` ausente (sem estimativas históricas); `peer_quality` corrente **ausente** |
| Setor / indústria / perfil / tipo | do **catálogo** (`valuation_universe` corrente) — os únicos campos correntes admitidos, declarados em `provenance.current_fields_admitted` |
| Estimativas de analistas, notícias, insiders, grades, institucionais, `peer_quality` | **ausentes**, contados em `provenance.pit_excluded_inputs` |
| Consenso (EUA) | última observação elegível **por casa** com `publishedDate ∈ (T−90 d, T]`, ≥ 3 casas, `currency` do alvo **presente e igual** à do mercado (verificada por campo; sem o campo → recusada); `horizon = "N/D"`; `published_at` = último alvo usado. **Nunca entra no motor** (a linha que o motor vê não tem consenso: `v3_tp == v3_internal_tp`, "TP sem consenso dentro"); o bloco é gravado ao lado (`decomposition.consensus`, cinco campos + hash). B3: sem consenso (contado) |
| Macro B3 | Selic: pacote derivado em T (`selic_package_at`: observações com `available_at ≤ T`, `as_of` = data económica, hash recomputado, `derived_from` aponta o payload de origem) do snapshot PIT `B3_BCB_SELIC_HISTORY` (`--fetch`) ou, na sua falta, do histórico vivo `valuation_macro_history/B3_SELIC_REGIME`; taxa livre de risco B3 = última Selic ≤ T (`b3_risk_free_source = "bcb_sgs_432_at_T"`, declarado — o shadow usa o Tesouro prefixado 5 a do V2, sem história) |
| Macro EUA | curva 3Y/10Y na última data ≤ T com ambos os tenores, `available_at` = meia-noite UTC seguinte (convenção do módulo macro), validada por `validate_us_curve_package`; `macro_as_of` = essa data; fonte: snapshot PIT `US_EODHD_TREASURY_HISTORY` (`--fetch`; o snapshot vivo só guarda a última observação) |
| Calibração | último snapshot `valuation_v3_calibration/<M>_CALIBRATION` publicado **antes de T** (`outputs.factor`); senão `absent_at_T` → fator 1,0 marcado. **Não existe produtor desse tipo nesta árvore**: hoje é sempre `absent_at_T` (interpretação declarada) |
| Admissibilidade por nome | ≥ 90 sessões válidas ≤ T na safra pinada (`MIN_VALID_SESSIONS`), verificada na corrida; nome inadmissível é contado em `not_evaluable`, nunca presumido do calendário |

O mercado irmão dos EUA (NASDAQ ↔ NYSE) **não** é carregado como par na mesma corrida (cada mercado tem a sua própria safra pinada); declarado e contado (`peer_market_<M>:not_loaded_in_this_run`). Desvio declarado face ao §3 ("medianas de pares dos dois mercados EUA").

## Preços: safra pinada, `T` só como data económica (desenho §2; auditor i)

`PinnedPrices` resolve **uma vez, no arranque da corrida**, a safra `valuation_price_history` do mercado (`vintage(available_before = agora)` → `publication_id`, `price_snapshot_id`, `available_at`, `bars_sha256`), grava-a no manifesto e **lê todos os símbolos por um corte igual a `available_at + 1 µs`** — o único corte que resolve exatamente essa publicação —, conferindo em cada leitura que `series().publication_id` é a pinada. Uma publicação nova a meio da corrida nunca entra (teste: safra dobrada publicada depois do primeiro símbolo; todos os preços continuam da pinada; a corrida seguinte pina a nova e tem outro `run_key`). Uma publicação pinada que deixe de resolver (`status ≠ ok` ou outro `publication_id`) é **recusa**, nunca substituição. `T` filtra `session_date ≤ sessão de T`; nunca é usado como corte de captura. Sessões fora do calendário não existem na série (o produtor só grava sessões do calendário).

## Identidade e idempotência (desenho §4; auditor ii)

- `run_key = sha256(canonical_json([source_version, market, T, manifest]))` — JSON canónico (chaves ordenadas, sem espaços), **nunca `hash()` do Python**. `source_version = "pit-rerun-v1+<sha do módulo>"`. O manifesto contém: hashes dos ficheiros de implementação, identidade do motor e da regra de buy-in (com os parâmetros neutros), todas as referências de snapshots (ids, `payload_sha256`, `fetched_at`, `symbol_sha256`), a safra de preços pinada, os pacotes macro derivados (hash de origem e derivado), a calibração, as regras de disponibilidade e de consenso.
- Snapshot: `entity_key = <M>_PIT_<run_key[:16]>`, `inputs = {run_key, market, as_of, source, source_version, manifest, supersedes?}`, `outputs = {rows (resultados do motor), summary, not_evaluable, prediction_identities [[símbolo, row_sha256]…]}`; `snapshot_id` = `cycle_id` das predições, `published_at` = relógio da persistência (o mesmo das linhas).
- **Trava**: em memória, um `threading.Lock` por `run_key`; em PostgreSQL, `pg_advisory_lock(<primeiros 8 bytes do run_key como int64 com sinal>)` **de sessão**, numa conexão dedicada, mantida sobre a gravação do snapshot **e** das predições (são dois commits; `pg_advisory_xact_lock` não os cobriria — interpretação declarada do §4).
- **Completude = conjunto de identidades, não contagem**: dentro da trava, o conjunto `{(symbol, row_sha256)}` já gravado para o ciclo (`valuation_predictions_for_cycle(cycle, source=v3_2_shadow)`) é comparado com o calculado (as linhas recomputadas com o `cycle_id` e o `published_at` do snapshot existente). Igual → nada escrito (`idempotent = true`); subconjunto → as linhas em falta são inseridas sob o mesmo `cycle_id` (a UNIQUE recusa duplicados); identidade gravada fora do calculado → `PitRerunIntegrityError`.
- Insumos alterados → `run_key` novo; a corrida anterior do mesmo `(market, T)` é encontrada por `Database.latest_analysis_snapshot_by_inputs` (método aditivo) e nomeada em `inputs.supersedes`.
- Contraprovas em teste: duas execuções iguais → um ciclo, zero linhas novas; interrompida após metade das linhas → completada sem duplicar, com o conjunto de identidades igual ao gravado no snapshot; insumo alterado → ciclo novo com `supersedes`; duas threads concorrentes → um ciclo (uma `idempotent = false`, outra `true`, 6 linhas no total).

## Nenhum caminho lê `now` no cálculo económico (auditor iii)

`PitRerunService.compute(market, as_of, prices)` — resolução das fontes, filtros por T, `today` do motor, `macro_as_of`, corte do consenso — corre, no teste, com `datetime.now`/`today` substituídos por uma classe que explode em `valuation_pit_rerun`, `valuation_v3_engine`, `valuation_v2_engine`, `valuation_v3_shadow`, `valuation_v3_macro`, `valuation_official` e `valuation_price_history`. O único relógio lido antes do cálculo é o da **seleção da safra** (`pin_vintage`, o agora real, só para escolher a publicação). `persist()` lê o agora real como `published_at` (≥ `T`, conferido; um relógio anterior a `T` é `PitRerunInputError`).

## Registro (desenho §1–§2)

`prediction_from_row(row, source="v3_2_shadow", source_version="pit-rerun-v1+<sha>", prediction_instant=T, published_at=agora, rerun_of=None, extra_provenance=…)` com: `tp = v3_internal_tp × fator de calibração`; `internal_tp = v3_internal_tp`; `buy_in = official_buy_in_v1(TPs dos modelos, official_entry_discount_v1(mercado, 50, 50), média)` — `risk_score`/`valuation_confidence` **neutros (50/50), declarados** em `provenance.buy_in_parameters` (não há modelo de risco ponto-no-tempo; interpretação); bandas do motor; `methods` = TP por modelo; bloco de consenso só quando datado ≤ T (senão nulos explícitos).

`decomposition.provenance` (o `extra_provenance` é mesclado depois dos campos fixos de `prediction_from_row`, hasheado com a linha e reconstruído pelo leitor PostgreSQL como qualquer outro campo): `engine = "ValuationV3Engine@<sha do módulo do motor>"`, `engine_path`, `buy_in_rule = "official_buy_in_v1@<sha do módulo>"`, `buy_in_parameters`, `price_vintage {publication_id, available_at, historical_vintage: "N/D"}`, `availability_rule`, `availability_hypotheses`, `pit_excluded_inputs`, `current_fields_admitted`, `beta`, `eligible_periods`, `macro`, `calibration {status, factor, snapshot_id}`, `run_key`, `consensus_in_engine = false`, `diagnostic_only = true`; `source_manifest_sha256` = hash do manifesto; `rerun_of = null`.

O `row_sha256` reproduz-se após a viagem de ida e volta pelo `NUMERIC` (`Database._numeric_param`: `Decimal(repr(x))`) — teste com o tuplo de colunas do leitor `Database._prediction_record`.

## Fases e CLI (desenho §5)

```
python -m app.valuation_pit_rerun --market M --fetch [--symbols A,B] [--no-macro]
python -m app.valuation_pit_rerun --market M --rerun --as-of 2024-06-14T18:00:00-03:00 [--detail PATH]
```

- `--fetch` (`PitFetchService`): **uma leitura por símbolo** — payload **bruto** EODHD `/api/v1.1/fundamentals/<sym>.<sufixo>` (o filtro causal acontece no `--rerun`); para NASDAQ/NYSE também o histórico FMP `/stable/price-target-news` (paginado; **interpretação**: `FmpClient` não tem endpoint de histórico por casa; o payload atual da FMP não traz `currency`, logo, pela regra do §3 "verificada por campo, senão consenso ausente", o consenso ficará ausente até o provedor expor a moeda — declarado); macro: BCB SGS 432 (15 anos, blocos de 4 anos) → `B3_BCB_SELIC_HISTORY`, EODHD `US3Y.GBOND`/`US10Y.GBOND` via `daily_bars` → `US_EODHD_TREASURY_HISTORY`. Tudo gravado como `valuation_pit_source/<M>_<PROVIDER>_<sha256(símbolo)[:16]>` com `fetched_at` real e `payload_sha256` (`outputs.payload` = payload bruto; `inputs.symbol` guarda o nome no banco privado). Stdout: só contagens — o teste confere que nenhum símbolo aparece. Requer a autorização do dono (§7–§8 do desenho); nunca durante pregão, fases noturnas ou janelas de ensaio (regra operacional: o módulo não a impõe por relógio — o `--fetch` é uma ordem manual).
- `--rerun` (`PitRerunService`): sem rede — o leitor de preços é construído sobre `_NoNetworkHttp` (`calls` fixado em 0); lê só snapshots + série. `--as-of` com fuso obrigatório. `--detail`: ficheiro privado (`O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`, `fchmod 0600`, fsync); caminho existente ou symlink recusado pelo parser antes de correr. Stdout: o recibo agregado (`run_key`, `cycle_id`, `idempotent`, `supersedes`, contagens, `pit_excluded_inputs`, `macro_as_of`, `price_vintage`) — sem símbolos.
- `main(argv, database=…, settings=…, http=…)` aceita injeções para teste; em produção constrói `Database(get_settings())` e o cliente HTTP dos workers.

## Testes (`tests/test_valuation_pit_rerun.py`, 19)

Disponibilidade (evidência EUA / hipótese B3 rotulada, nunca "publicação original"; a corrida no dia anterior ao `filing_date` não vê o trimestre); fixture envenenada (pura + ponta a ponta); pacotes macro em T; regra do consenso; **equivalência do motor** com o caminho do shadow (mesmo `loaded` sintético, NASDAQ e B3, resultados idênticos); registros e snapshot (campos do §1–§2); relógio explosivo no cálculo económico + relógio real na persistência; safra pinada (publicação a meio da corrida; recusas); `run_key` canónico e chave da trava; duas execuções iguais; interrupção; insumo alterado (`supersedes`); concorrência; recusa de `v3_2_shadow` na seleção; hash após `NUMERIC`; painel classifica tudo `retrospective` (decisão `UNMEASURED`/`no_live_cohort`, horizonte 126 rotulado "à parte"); `--fetch`; CLI (`--as-of` ingénuo recusado, detalhe 0600 exclusivo, symlink recusado, nada nominal); `T` sem 90 sessões válidas → nada avaliado, tudo explicado.

## Limitações a declarar na leitura (desenho §7)

TP sem sinais sem história (estimativas, qualidade forward, peer quality); calibração sempre `absent_at_T` (fator 1,0) nesta árvore; consenso sem horizonte atestado (`N/D`) → o painel não o compara (e, com o payload atual da FMP sem `currency`, ausente); B3 sem consenso; lag B3 hipotético; vintage original `N/D`; beta contra proxy equiponderado do universo (não um índice); pares só do mercado da corrida; buy-in com parâmetros neutros declarados; sem controlo de sobrevivência (o catálogo é o universo **corrente**); admissibilidade por símbolo/T verificada na corrida (90 sessões válidas por nome). A comparação byte a byte com um T recente com snapshots reais (§1) fica para depois do merge e do `--fetch` autorizado: não há snapshots PIT reais nesta árvore.
