# Valuation — Decisor V1 (sombra)

Direção do dono de 17/10/2026: o Valuation passa a ser quem decide compra / não-compra. Esta é a V1, **em sombra**:
grava veredictos imutáveis por nome por noite, não muda nenhum número servido, não escreve a seleção oficial e não
toca tabelas, ordens ou posições do R2D2. Código: `backend/app/valuation_decision.py`; migração `db/052_valuation_decisions.sql`.

## Veredicto

| Veredicto | Quando |
|---|---|
| `COMPRA_PERMITIDA` | todos os portões passaram (`reason_codes = ["ALL_GATES_PASSED"]`) |
| `OBSERVAR` | TP confiável, mas sem permissão: sem margem hoje (`PRICE_ABOVE_BUY_IN`, `TP_MARGIN_INSUFFICIENT`) ou insumo da margem ainda não medido (`E_PROFILE_WARMING_UP`, `E_PROFILE_UNAVAILABLE`, `MARKET_RATE_UNAVAILABLE`) |
| `VETO` | o TP ou seus dados não são confiáveis agora (frescor, qualidade, defeito de dado); lista **todos** os códigos que falharam, inclusive os de OBSERVAR |

## Regras

* **TP** = a linha oficial **servida** (`official_rows` / `official_row` por UMA geração): `our_tp`/`buy_in` do registro —
  os internos quando a geração seleciona `official_internal_v1`. O decisor nunca calcula, ajusta ou mistura TP.
* **Margem**: `ask_ou_preço <= buy_in` **e** `TP × (1 − e_profile) >= ask_ou_preço × (1 + h_market)`. Com ask disponível,
  ele é o preço de execução (lado conservador).
  * `e_profile` = erro absoluto **mediano** medido pelo produtor para o `valuation_profile` do nome
    (`valuation_calibration/<M>_POWER_MODEL`, `metrics[perfil].median_absolute_error_percent`, chave nova e apenas
    diagnóstica nos dois screeners — nenhum fator a lê). Base **só preço** nos dois mercados: a B3 já tira o dividendo
    esperado da expectativa; nos EUA a expectativa da métrica é o `upside_percent` (o retorno total esperado soma o
    dividend yield e o realizado é só preço — o fator continua com as amostras dele, nenhum número servido muda). Só vale
    com calibração `active`, horizonte observado em 60–150 dias, perfil com o mínimo de amostras e snapshot com até 7 dias;
    caso contrário, sem permissão.
  * `h_market` = `(1 + taxa) ^ horizonte − 1 + prêmio` (TP de 12 meses; prêmio 0 por padrão). Fonte: a primeira
    **fresca** (≤ 10 dias) da ordem declarada — B3: BCB SGS 432 (observações datadas), depois a Selic do ciclo oficial B3
    (`outputs.macro.selic`); US: T-bill de 13 semanas (pacote do cash-yield do R2D2), depois a 5Y interpolada (pacote
    validado como o V3 valida, com idade medida pela data de observação dos yields, nunca pelo `as_of` do pacote). A Selic
    do ciclo é **sem data**: o ciclo grava só o valor, e o produtor cai na constante do governador quando brapi e BCB
    falham — não dá para distinguir. Ela só conta se o bloco a listar em `undated_rate_sources_admitted` (padrão: vazio),
    e então fica marcada `undated` no registro. Pacotes com hash que não confere, ou observação ainda não disponível no
    relógio da rodada, são ignorados. A fonte usada fica nomeada no registro.
* **Frescor (VETO)**: `tp_stale` marcado na linha; sessão do TP mais de 1 sessão atrás da última sessão completa;
  fundamentos mais velhos que um trimestre + 45 dias (92 + 45 = 137 dias) ou sem data; preço que andou mais de X % desde o
  corte (preço do registro do TP) ou sem preço; preço **não observado depois do fechamento da última sessão completa**
  (`PRICE_SESSION_STALE`). O preço do próprio corte é da sessão do TP: com o TP 1 sessão atrás (tolerado), a sessão que
  faltou nunca foi observada e o movimento leria 0 %. Vale um ciclo de universo publicado depois daquele fechamento
  (mesmo que a geração mantenha o ciclo antigo) ou uma cotação fresca.
* **Qualidade (VETO)**: não validado (`tp_validation_status` quando o produtor emite — B3 —, senão `signal_quality` — US);
  dispersão de métodos acima do limite ou desconhecida; confiança abaixo do limite ou desconhecida; qualquer marca de
  defeito de dado (`data_defect`, `data_defects`).

## Bloco de limiares (a congelar no PREREG)

Todos em `DecisorThresholds` (um único bloco, com hash `thresholds_sha256` gravado em cada registro). Padrões atuais:

| Limiar | Padrão |
|---|---|
| `max_tp_age_sessions` | 1 |
| `fundamentals_quarter_days` + `fundamentals_grace_days` | 92 + 45 |
| `max_price_move_percent` (o X) | 5,0 |
| `max_quote_age_minutes` (cotação de quem chama, só em dry run) | 15 |
| `max_method_dispersion_percent` | 45,0 (o mesmo dos produtores) |
| `min_valuation_confidence` | 70,0 (o mesmo dos produtores) |
| `min_profile_samples` / horizonte | 15 / 60–150 dias |
| `calibration_max_age_days` | 7 |
| `allow_global_error_fallback` | falso |
| fontes de taxa B3 / US | SGS 432 → ciclo B3 / T-bill 13s → 5Y |
| `undated_rate_sources_admitted` | vazio (a Selic do ciclo não conta) |
| `market_rate_max_age_days` | 10 |
| `tp_horizon_years` / `market_premium` | 1,0 / 0,0 |

Congelamento: o commit que cita o PREREG grava `PREREG_THRESHOLDS_SHA256 = thresholds_sha256()`; a partir daí uma rodada
com qualquer outro bloco é recusada (`ValueError`) e os registros passam a dizer `prereg_frozen = true`.

## Registros (`valuation_decisions`, migração 052)

Mesma disciplina de `valuation_predictions`: dois relógios (`prediction_instant` = relógio da rodada; `published_at` lido
imediatamente antes do insert, nunca antes — CHECK), sessão do veredicto pelo calendário da bolsa (nunca data civil),
identidade do TP lido (geração, fonte, ciclo, hash da linha, instante), `inputs` com a procedência de cada insumo
(calibração, taxa, preço, campos da linha) + `inputs_sha256`, `checks` com os números de cada portão, `row_sha256`
canônico recomputado por todo leitor (linha que não confere não é servida). Append-only (UPDATE/DELETE/TRUNCATE recusados),
idempotente por `(run_id, market, symbol)`, `mode` só `shadow`: veredicto que age exige migração e ordem novas.
Causal: o TP vem da geração **em vigor no relógio da rodada** (`generation_at`, nunca uma posterior — um replay decide o
que aquela noite viu), e linha servida com `prediction_instant` depois do relógio não é decidida
(`tp_after_run_instant` no recibo).

## Fase noturna

`valuation_worker`, fase `decisor_shadow`, **desligada por padrão** (`C3PO_VALUATION_DECISOR_SHADOW=true` liga). Roda por
último entre as fases off-hours (depois do corte oficial e de toda fase existente; nunca atrasa uma delas). A noite está
feita quando a última rodada decidiu sobre a geração em vigor: uma geração ativada depois, dentro da janela (retry do
canônico), é decidida de novo. O recibo da rodada é agregado (contagens por mercado, veredicto e código, cotações
recusadas) — não nomeia símbolo. CLI: `python -m app.valuation_decision --dry-run` (nada gravado), `--run` (recusado com a
flag desligada), `--verdict MERCADO:SÍMBOLO`.

`run_shadow` é **dry run por padrão**; grava só com `write=True` **e** a flag ligada (quem quer que chame — senão
`ValueError`). A flag é lida do ambiente do processo (`app/valuation_env.py`, não `Settings`: `config.py` entra no hash do
pacote do R2D2 V2); `run_shadow(enabled=…)` a fixa só para quem chama explicitamente (testes). Rodada com cotações de quem chama (`quotes`) é sempre dry run: nada intradiário substitui os veredictos
noturnos que o laboratório lê. Cotação sem `as_of` legível, com `as_of` depois do relógio da rodada ou mais velha que
`max_quote_age_minutes` é recusada (`quote_refused` na procedência) e a fonte noturna responde.

## Leitura pelo laboratório do R2D2

`latest_verdicts(database, mercado, símbolos, now=…)` / `latest_verdict(...)`: o laboratório **nomeia** os símbolos que
pergunta (`B3`, `NASDAQ`, `NYSE` ou `US`); nada enumera os nomes permitidos e não há rota HTTP. Cada resposta traz o
veredicto, os códigos, o TP lido e sua identidade, e `current` = `session_current` (decidido para a última sessão
completa em `now`) **e** `tp_served` (a geração em vigor em `now` ainda serve, para o símbolo, a mesma linha — mesmo
`tp_row_sha256` — que o veredicto leu: admissão dirigida de outro nome mantém; troca de fonte ou rollback não). Veredicto
que não é current sai com `effective_verdict = VETO` e `effective_reason_codes` com o motivo (`VERDICT_NOT_CURRENT`,
`VERDICT_TP_NOT_SERVED`): nenhuma permissão sobrevive à sua noite nem ao seu TP.

## Pendências declaradas

* Os limiares acima são propostas até o PREREG.
* `e_profile` só existe depois que os produtores gravarem a métrica nova na calibração (próximo ciclo após o deploy);
  até lá, todo nome fica sem permissão (`E_PROFILE_UNAVAILABLE`).
* **Decisão do PREREG sobre `e_profile`**: a métrica é o erro de RETORNO em ~90 dias (|realizado − esperado no período|),
  não um erro do TP em 12 meses, e é aplicada como desconto sobre um TP de 12 meses. O PREREG decide se aceita esse proxy,
  se o escala para o horizonte do TP ou se pede uma métrica de erro de TP (por exemplo, da frente de acurácia).
* **Taxa da B3**: com o bloco padrão, o `h_market` da B3 depende do pacote SGS 432 (`valuation_macro_history/B3_SELIC_REGIME`)
  com observação de até 10 dias — hoje esse pacote é atualizado pelo operador (`python -m app.valuation_v3_macro`), não
  por fase noturna. Sem ele, todo nome B3 fica `OBSERVAR` (`MARKET_RATE_UNAVAILABLE`). O PREREG escolhe: atualização
  noturna do pacote no servidor, o produtor B3 passar a gravar a data de observação da Selic, ou admitir a Selic sem data
  do ciclo (`undated_rate_sources_admitted`) sabendo do risco da constante.
* **Portões ainda inertes**: nenhum produtor emite hoje `tp_stale`, `data_defect` ou `data_defects` — `TP_STALE_FLAG` e
  `DATA_DEFECT` passam todo nome em produção. O PREREG não os conta como checagens até a frente XBRL (migração 053) ou
  outro produtor gravar a marca; se ela vier em outra estrutura, o decisor precisa de um leitor para ela. **Estado na
  integração de 17/10:** a frente as-filed grava a marca dos EUA em outra estrutura — `valuation_tp_staleness`
  (053, `state = stale`, lida por `valuation_asfiled.stale_us_tps`) — e o decisor **ainda não a lê**: com
  `C3PO_VALUATION_ASFILED_ENABLED` e `C3PO_VALUATION_DECISOR_SHADOW` ligadas, um TP anterior a um 8-K 2.02 ou 10-Q/10-K
  aceito depois do corte não é vetado por isso (sai `COMPRA_PERMITIDA` se o resto passar). O leitor tem de ser
  causal (marcas com `recorded_at` ≤ relógio da rodada e sem `cleared` até ele; `stale_us_tps` hoje lê tudo o que
  existe) e entra como código de veto antes do recibo de congelamento do decisor.
* Preço depois do corte: hoje vem de ciclo de universo publicado depois do fechamento; a série de preços da V3.2
  (`valuation_price_bars`, migração 049, fase desligada por padrão) é a próxima fonte natural de fechamento por sessão.
