# V2 — contrato proposto do produtor de risco canônico V1

Estado: módulo puro e adaptador isolado, sem ligação operacional. Este contrato
precisa da auditoria do Fable antes da ligação. Não fornece cobertura real dos
550 nomes, não consulta providers/banco e não chama os fluxos V1, `generate`,
`screen`, `_us_candidates`, admissão ou BUY. Não altera a política assinada nem
define um TTL novo. O executor/produtor e suas provas de disponibilidade ainda
precisam ser implementados e auditados.

## Origem e alcance da equivalência

`app/r2d2_v2_risk_source.py` expõe:

```python
canonical_risk_score(inputs: CanonicalRiskInputs) -> float
adapt_canonical_risk(
    inputs: CanonicalRiskInputs,
    evidence: Mapping[str, ComponentEvidence],
    *, computed_at: datetime | None, available_at: datetime | None,
    decision_at: datetime,
) -> dict
```

Família `CANONICAL_ONLY_V1`, versão `1.0.0`. A origem é
`OnePagerService._analyze:531–546` e os auxiliares `:996–1048`, na revisão
`6083d7420746434426a11134b8edf0ba4b60b6b0`; SHA256 do `one_pager.py`:
`e49265da0cfc4cd10ab8e94d826ff8be38ee1d278137769a62d3c9a86f006e0d`.
O pacote que ligar o produtor deverá também pinar os bytes deste módulo; o hash
da origem, sozinho, não autentica uma implementação futura.

O kernel conserva a ordem das operações, pesos e limites do bloco original:

```text
r = 32
beta presente:              r += clamp((beta − 0.85) × 24, −8, 25)
dívida/EBITDA presente:     r += clamp((dívida/EBITDA − 1.5) × 7, −8, 24)
crescimento do lucro < 0:  r += min(16, abs(crescimento) × 38)
FCF < 0:                  r += 9
r -= sinal_insider × 8
r -= sinal_institucional × 8
r -= sinal_grades × 6
resultado = clamp(r, 15, 90)
```

Os sinais preservam o saldo entre contagens positivas e negativas, com peso
reduzido até quatro operações insider, cinquenta posições institucionais ou
cinco upgrades/downgrades. Ações de grades diferentes das strings exatas
`upgrade` e `downgrade` não entram no sinal, como no original.

Esta equivalência é do bloco canônico com **inputs já normalizados e válidos**.
Não inclui `shared_valuation`, que pode substituir o resultado no OnePager,
nem a fórmula provisória de preço/liquidez do V1. O backfill V1 chama o mesmo
bloco sem os enriquecimentos opcionais; isso não comprova ausência verificada
desses dados. A escolha canônico-only não afirma reproduzir as três famílias
presentes no histórico `decision_snapshot.risk_score`.

## Inputs explícitos e evidência

`CanonicalRiskInputs` é uma dataclass congelada com os sete componentes:

| Campo | Valor normalizado | Cobertura necessária para `READY` |
|---|---|---|
| `beta` | Número positivo ou `None` | Medida identificada e disponível |
| `debt_to_ebitda` | Razão assinada ou `None` | Dívida e EBITDA/TTM identificados, unidades e períodos compatíveis; TTM negativo pode produzir razão negativa no original |
| `earnings_growth` | Razão assinada ou `None` | Medida/períodos identificados; sem converter porcentagem silenciosamente |
| `free_cashflow` | Valor assinado ou `None` | Períodos e unidades identificados |
| `insider_activity` | `InsiderActivity(total_count, buy_count, sell_count)` ou `None` | Janela/população cobertas, inclusive quando a contagem é zero |
| `institutional_positions` | `InstitutionalPositions(new_positions, increased_positions, reduced_positions, closed_positions)` ou `None` | Período e população cobertos |
| `recent_grade_actions` | Tupla de ações ou `None` | Janela/população cobertas, inclusive uma tupla vazia |

Números devem ser `int`/`float` nativos, finitos e sem `bool`; contagens devem ser
inteiros não negativos. Insider buy+sell não pode exceder total. Tipos,
contagens inconsistentes e relógios estruturalmente inválidos lançam
`ValueError` antes de qualquer resposta `READY`; não geram score substituto.
O adaptador não arredonda nem transforma strings numéricas.

O produtor upstream deverá reproduzir/documentar a preparação dos escalares
que precede o bloco original: `earningsGrowthAnnual` normalizado como razão,
beta positivo, escolha de dívida/EBITDA e FCF, incluindo ordenação e composição
dos períodos TTM. O OnePager usa fallbacks e pode somar menos de quatro valores
presentes. Este módulo não faz essa ingestão nem considera esses fallbacks uma
prova de cobertura. Não basta copiar os escalares sem evidência dos inputs.

`evidence` contém exatamente as sete chaves acima. Cada `ComponentEvidence`
declara `response_complete`, `coverage_verified`, `source_id`, `source_version`,
`payload_sha256`, `source_at`, `available_at` e `coverage_description`. A descrição
identifica janela/população e transformação dos inputs. Hashes e flags são
**atestações do produtor a auditar**, não autoprova: este módulo não lê o payload
externo nem comprova retrospectivamente a hora em que foi emitido. Nenhum campo
booleano transforma uma fonte incompleta em fonte certificada.

## Relógios e resultado

Todos os relógios são conscientes de fuso e saem em UTC. Para `READY`:

```text
cada source_at <= cada available_at <= computed_at <= available_at do risco <= decision_at
```

`computed_at` é a conclusão factual da avaliação do score, inclusive quando
conclui sem valor por falta de cobertura. `available_at` é sua disponibilidade
factual. O futuro executor deverá emitir esses instantes a partir da execução
real e vinculá-los à evidência; a função pura apenas recebe os valores para
validação/testes. Não usa `datetime.now()` e não gera timestamps retroativos.

Releitura e republicação da mesma avaliação preservam os relógios originais.
Um transporte posterior pode ter seu próprio recibo, separado. No screener
legado, atualizar `quote.as_of` não recalcula risco; portanto esse relógio não
pode substituir `computed_at`. O adaptador não recebe `quote.as_of`. O prazo
de dez segundos de bid/ask não é um TTL de risco; a política específica de
atualização/freshness do produtor continua pendente de definição e auditoria.

| Estado | Significado | Campo `risk` |
|---|---|---|
| `INCOMPLETE` | Resposta ainda não concluída/disponível no instante da decisão | `None`; não fabricar disponibilidade |
| `COMPLETED_NULL` | Resposta concluída, mas valor/cobertura/proveniência/causalidade insuficiente | Shape da porta, `value=None`, relógios factuais da avaliação |
| `READY` | Todos os sete componentes presentes, causalmente válidos e com cobertura atestada | Shape da porta, valor em precisão integral |

O kernel aceita `None` para reproduzir a matemática original — todos ausentes
resultam em32 — mas o adaptador nunca publica esse resultado como `READY`.
Cobertura desconhecida não vira zero,55 ou100. Zero insider/13F e grades vazias
são compatíveis com `READY` apenas quando sua cobertura é explicitamente
atestada. A saída sempre informa `coverage.independently_verified=false` e
`production_connected=false`.

O `risk` concluído tem as chaves exatas `value`, `producer`, `source_at`,
`available_at`; não é um envelope completo da porta V2. O futuro montador deverá
preservar um completed-null e seus diagnósticos. Quando todos os componentes do
candidato estiverem completos, essa resposta deve congelar `DATA_INELIGIBLE`,
sem nova tentativa baseada no score melhorado. O estado/primeira resposta é do
coletor; este módulo puro não implementa armazenamento, freeze ou retries.

O resultado inclui recibo **privado** `calculation` com inputs normalizados e
evidências, `calculation_sha256` e `self_sha256`. A canonicalização usa JSON
ordenado, compacto, ASCII e sem NaN. `self_sha256` exclui sua própria chave.
O hash do cálculo não inclui `decision_at`; uma releitura com decisão posterior
muda o recibo de observação, sem rejuvenecer o cálculo. O futuro executor deve
guardar esses dados com controle de acesso; não há gravação ou publicação aqui.

## Validação e pendências de ligação

Os testes usam o `_analyze` atual como oráculo diferencial com objeto sem
construtor/DB, incluindo limites, ausência e sinais finos. Exercitam tipos
estritos, causalidade, completed-null, cobertura vazia verificada, precisão e
releitura com cotação posterior. Não consultam providers ou produção.

Antes da ligação: Fable audita este contrato; define-se o produtor dos sete
inputs, a cobertura exata de todos os nomes de `L_D`, os recibos causais e a
política de atualização; testa-se integração com a porta e a persistência da
primeira resposta. A atestação de cobertura, o hash de payload e os relógios
precisam de autoridade externa verificável. Não há promessa de disponibilidade
dos550, execução às10h ou prontidão operacional neste artefato.
