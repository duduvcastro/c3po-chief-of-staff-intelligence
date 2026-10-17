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
    diagnóstica nos dois screeners — nenhum fator a lê). Só vale com calibração `active`, horizonte observado em 60–150
    dias, perfil com o mínimo de amostras e snapshot com até 7 dias; caso contrário, sem permissão.
  * `h_market` = `(1 + taxa) ^ horizonte − 1 + prêmio` (TP de 12 meses; prêmio 0 por padrão). Fonte: a primeira
    **fresca** (≤ 10 dias) da ordem declarada — B3: a Selic do ciclo oficial B3 (`outputs.macro.selic`), depois BCB SGS 432;
    US: T-bill de 13 semanas (pacote do cash-yield do R2D2), depois a 5Y interpolada. Pacotes com hash que não confere
    são ignorados. A fonte usada fica nomeada no registro.
* **Frescor (VETO)**: `tp_stale` marcado na linha; sessão do TP mais de 1 sessão atrás da última sessão completa;
  fundamentos mais velhos que um trimestre + 45 dias (92 + 45 = 137 dias) ou sem data; preço que andou mais de X % desde o
  corte (preço do registro do TP) ou sem preço.
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
| `max_method_dispersion_percent` | 45,0 (o mesmo dos produtores) |
| `min_valuation_confidence` | 70,0 (o mesmo dos produtores) |
| `min_profile_samples` / horizonte | 15 / 60–150 dias |
| `calibration_max_age_days` | 7 |
| `allow_global_error_fallback` | falso |
| fontes de taxa B3 / US | ciclo B3 → SGS 432 / T-bill 13s → 5Y |
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

## Fase noturna

`valuation_worker`, fase `decisor_shadow`, **desligada por padrão** (`C3PO_VALUATION_DECISOR_SHADOW=true` liga). Roda por
último entre as fases off-hours (depois do corte oficial e de toda fase existente; nunca atrasa uma delas). A noite está
feita quando a última rodada decidiu sobre a geração em vigor: uma geração ativada depois, dentro da janela (retry do
canônico), é decidida de novo. O recibo da rodada é agregado (contagens por mercado, veredicto e código) — não nomeia
símbolo. CLI: `python -m app.valuation_decision --dry-run` (nada gravado), `--run` (recusado com a flag desligada),
`--verdict MERCADO:SÍMBOLO`.

## Leitura pelo laboratório do R2D2

`latest_verdicts(database, mercado, símbolos, now=…)` / `latest_verdict(...)`: o laboratório **nomeia** os símbolos que
pergunta (`B3`, `NASDAQ`, `NYSE` ou `US`); nada enumera os nomes permitidos e não há rota HTTP. Cada resposta traz o
veredicto, os códigos, o TP lido e sua identidade, e `current` (decidido para a sessão em vigor em `now`). Veredicto de
outra sessão sai com `effective_verdict = VETO` e `effective_reason_codes = ["VERDICT_NOT_CURRENT"]`: nenhuma permissão
sobrevive à sua noite.

## Pendências declaradas

* Os limiares acima são propostas até o PREREG.
* `e_profile` só existe depois que os produtores gravarem a métrica nova na calibração (próximo ciclo após o deploy);
  até lá, todo nome fica sem permissão (`E_PROFILE_UNAVAILABLE`).
* `tp_stale` é lido da linha servida quando presente; se a frente XBRL publicar a obsolescência em outra estrutura
  (migração 053), o decisor precisa de um leitor para ela.
