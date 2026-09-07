# V2 — parser de earnings e fronteira de comprovação de cobertura

Estado: **preparo isolado para auditoria; não pronto para produção nem integrado à porta**.
Nenhuma requisição ao provedor, persistência, coleta, configuração ou ativação é
implementada aqui. `production_ready=false` e `port_payload_emitted=false` são
constantes da saída pública, inclusive nos testes positivos de verificação.

O módulo `app/r2d2_v2_earnings_source.py` usa somente biblioteca padrão. O parser
é puro. A avaliação não faz I/O próprio; o único ponto extensível é um verificador
injetado, cuja implementação deve ser auditada separadamente e ser somente-leitura.
Não há verificador real de completude de earnings neste pacote.

A avaliação de cobertura abaixo permanece como fronteira do contrato anterior.
A EMENDA 3 rev3 (`3319407afcd7760668e6ec73bb4686ecb95a38eecf47fc157050899f80a6cc9c`)
propõe substituí-la por três evidências validadas e recomputação de exclusão.
Essa integração depende do conjunto de assinaturas e de um delta auditado da
porta e dos eventos vivos. As correções do parser aqui não ativam essa política.

## Contrato e referências fixas

- Observação: `R2D2_V2_EARNINGS_OBSERVATION_V2` (diagnósticos por linha/símbolo).
- Avaliação: `R2D2_V2_EARNINGS_COVERAGE_V1`.
- Manifesto: `eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0`.
- Emenda: `3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4`.
- Porta mantida: `V2_SHADOW_SOURCE_SNAPSHOT_V2`, sem alteração de seu esquema.
- Escopo de atestado: `ALL_KNOWN_ANNOUNCEMENTS_FOR_SYMBOL_AND_WINDOW`.

O hash do corpo é SHA256 dos bytes exatos; o hash do recibo é SHA256 de seu JSON
com chaves ordenadas, separadores compactos, ASCII e números finitos, com relógios
normalizados para UTC. São vínculos de integridade, não provas de completude ou
autoridade. O limite de 64 MiB é uma proteção de memória, não um limite de cobertura
do provedor. Não foram definidos TTL, cadência ou tolerância de atraso.

## API e formatos

```python
parse_earnings_response(raw: bytes, receipt: EarningsReceipt) -> EarningsObservation

assess_earnings_coverage(
    observation: EarningsObservation,
    *, symbol: str, decision_at: datetime, maturity_at: datetime,
    evidence: CoverageEvidence | None = None,
    verifier: CoverageVerifier | None = None,
) -> EarningsAssessment
```

`EarningsReceipt` contém apenas parâmetros públicos da consulta e metadados
factuais: tupla de símbolos EODHD exatos (vazia representa consulta sem filtro),
datas `request_from/request_to`, `request_started_at`, `response_received_at`,
`available_at`, status HTTP, `body_sha256`, `transport_complete` e `content_type`.
Não recebe token, URL autenticada ou headers de autorização. Todos os relógios
devem ter offset; início ≤ recebimento ≤ disponibilidade. Datas invertidas,
hash errado, símbolos duplicados e booleanos no lugar de inteiros são rejeitados
com código controlado. O recibo é um input do futuro coletor: este parser não
observou o transporte e não pode comprovar que o coletor disse a verdade.

`EarningsObservation` conserva os bytes completos em campo privado e uma tupla
imutável de eventos válidos reconhecidos. Um evento conserva símbolo, data de
anúncio, fim do período fiscal, timing BMO/AMC/null e registro original canônico.
Uma linha inválida não desaparece do corpo privado. `row_diagnostics` registra
índice, símbolo válido quando identificável, código controlado e caráter bloqueante.
`status_for_symbol()` devolve `INVALID_ROWS` somente para o símbolo afetado.
Quando não há identidade confiável, a incerteza aplica-se a todos os símbolos:
não se pode atribuir silenciosamente a linha inválida a outro nome. Isso não
transforma o corpo JSON em estruturalmente inválido nem descarta os fatos válidos.

Estados do parser: `OBSERVED`, `OBSERVED_WITH_DIAGNOSTICS`,
`INCOMPLETE_TRANSPORT`, `HTTP_ERROR`, `INVALID_BODY`.
`INVALID_BODY` fica reservado a falhas estruturais/do envelope, inclusive JSON
malformado, chaves duplicadas, constantes não finitas e ecos incompatíveis.
Somente um HTTP200 JSON íntegro pode ser observado. Isso ainda implica
`feed_coverage=UNKNOWN`: uma lista vazia não é atestado negativo. Valores EPS null
continuam null; nenhum deles cria estado de anúncio confirmado ou cancelado.
Campos desconhecidos em linhas geram diagnóstico sem descartar a linha ou interpretar
esses campos como autoridade. Enums/tipos/datas inválidos bloqueiam o símbolo.
Datas fora da janela e repetições do período fiscal geram diagnósticos sem bloquear
outros nomes: todas as datas e classificações observadas são preservadas para a
união conservadora; não há sobrescrita pela última revisão. O hook legado continua
independente e nunca recebe liberação de cobertura baseada apenas no parser.
`symbols:""` é aceito exclusivamente quando a requisição não tinha filtro; esse
eco não prova cobertura. O corpo real permanece item do rito de prontidão.

`public_summary()` omite símbolos, payload, referências nominais do atestado e
mensagens de erro externas. `to_private_dict()` acrescenta recibo, eventos, diagnósticos
por linha e o corpo
exato em base64. Essa saída é privada; seu chamador deverá persistir em localização
autorizada com permissões adequadas. Este módulo não abre arquivos nem faz logs.

## Três níveis distintos

1. **Transporte:** a declaração de recebimento completo + bytes e hash permite
   verificar integridade local. Não significa que o feed listou todos os eventos.
2. **Observação positiva:** uma linha pode demonstrar que o feed informou uma
   data, com a granularidade que forneceu. Não resolve ausência dos demais nomes.
3. **Cobertura:** exige prova independente referente ao símbolo e intervalo
   precisos, aos bytes e ao recibo. A ausência de um nome em lote não herda a
   cobertura de outro nome.

O `CoverageEvidence` é uma referência **não confiável** até a verificação externa.
Inclui `attestation_id`, `issuer`, hashes do contrato e da evidência externa,
hashes do corpo/recibo observados, símbolo, limites precisos de cobertura,
`known_as_of`, `published_at` e escopo. O módulo confere os vínculos e exige
`window_start ≤ decision_at ≤ maturity_at ≤ window_end`, além de
`known_as_of ≤ response_received_at ≤ published_at ≤ decision_at`.
O último relógio é a publicação do atestado vinculado a estes bytes, não a data
do anúncio. A disponibilidade da observação também não pode ultrapassar a decisão.

`CoverageVerifier(evidence, expected)` recebe uma expectativa imutável contendo
schema, pins, símbolo, parâmetros originais da consulta, hashes, decisão,
maturidade e relógios factuais. Só o retorno **literal `True`** permite `VERIFIED`.
Ausência do hook/evidência, exceção, retorno truthy não booleano, janela curta ou
vínculo incorreto mantém `UNKNOWN`. Erros atribuíveis a outro símbolo e avisos de
campos novos não contaminam a avaliação deste símbolo. Erros bloqueantes próprios
ou sem identidade e vínculos inválidos bloqueiam antes de chamar
o hook. Nenhuma mensagem arbitrária de exceção externa é propagada.

O verificador deverá consultar evidência já existente em autoridade independente,
verificar autoria, contrato de completude, validade temporal, revisões e a relação
entre o filtro de datas original e o intervalo preciso. Um callback que sempre
retorna True, que aceita um booleano do produtor ou que compara seu hash consigo
mesmo é **um stub**, não uma implementação aceitável. Python não transforma esse
hook em isolamento de segurança: ele é uma dependência confiável, sujeita a
auditoria. O teste positivo usa explicitamente um stub sintético e não constitui
evidência de cobertura real. As dataclasses de observação são objetos internos
produzidos pelo parser; não são um formato de desserialização de objetos externos.

## Granularidade, intervalos e causalidade

`event_at`, timezone, `provider_announced_at`, `provider_updated_at` e
`announcement_status` permanecem null. `report_date` não é `date` fiscal; BMO/AMC
não se torna 09:30/16:00, nem meia-noite UTC. O recibo local não se torna relógio
de atualização do provedor. Receber hoje um histórico não atribui disponibilidade
no passado.

Cobertura e compatibilidade temporal são saídas separadas. Mesmo com cobertura
externa comprovada, qualquer evento do símbolo mantém
`port_temporal_fields_complete=false` e `EVENT_PRECISE_TIME_UNAVAILABLE`, pois
a porta vigente exige o instante exato. Para conjunto vazio com prova externa
válida, o campo pode ser true; isso descreve somente a ausência desse impedimento
de formato e nunca emite payload ou autoriza produção. Estender a porta para
intervalos de tempo exige decisão e auditoria próprias; não foi feito aqui.

O teste local `request_from ≤ report_date ≤ request_to` detecta registros fora
dos limites declarados; não certifica a inclusividade ou o timezone do endpoint.
O hook recebe as datas originais para verificar essa semântica com a autoridade
externa. Não há conversão implícita de `from/to` para um intervalo de instantes.

Cobertura diz respeito a eventos **já conhecidos** na decisão. Não promete que
nenhum anúncio novo será publicado depois. Desaparecimento ou revisão de uma
linha não cria cancelamento automático, não modifica observações anteriores e
não libera retroativamente admissão. O módulo não implementa fluxo de eventos.

## Evidência documental ainda necessária

A documentação consultada não fecha cobertura negativa por símbolo nem fornece
relógios exatos/status de cancelamento necessários à adaptação direta. Há também
divergência oficial sobre `symbols` filtrar ou substituir as datas. Por isso não
existe implementação concreta do hook neste pacote. Fontes consultadas:
[calendário EODHD](https://eodhd.com/financial-apis/calendar-upcoming-earnings-ipos-and-splits),
[OpenAPI oficial](https://raw.githubusercontent.com/EodHistoricalData/EODHD-openapi/main/paths/calendar_earnings.yaml),
[orientação de atualização](https://github.com/EodHistoricalData/eodhd-claude-skills/blob/main/skills/eodhd-api/references/general/update-times.md).

## Validação local sintética

`tests/test_r2d2_v2_earnings_source.py` cobre vazio/negativa desconhecida, hook
ausente ou truthy, vínculos e relógios adulterados, ambos os extremos inclusivos,
um microssegundo insuficiente, BMO/AMC/null no interior e nas fronteiras, erros
HTTP, truncamento, chaves duplicadas, enums e números inválidos, EPS null,
desaparecimento sem cancelamento, duplicatas, lotes, divergências de datas/símbolos,
backfill não causal, offsets e privacidade de stdout/representações. Uma inspeção
AST restringe imports à biblioteca padrão e verifica ausência de primitivas de I/O.

```bash
PYTHONPATH=c3po/backend python -m pytest c3po/backend/tests/test_r2d2_v2_earnings_source.py -q
```

Nenhum teste consulta dados reais ou representa prova do comportamento do endpoint.
