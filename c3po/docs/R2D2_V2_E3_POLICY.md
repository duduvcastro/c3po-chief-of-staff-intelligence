# Validador puro da política E3 rev3

Norma: Emenda 3 rev3 `3319407afcd7760668e6ec73bb4686ecb95a38eecf47fc157050899f80a6cc9c`.
Manifesto de seis mãos: `1a927ca41df89ccb28a276726626672b7d76a9e828f12e4fc5b126860dbb4e72`.
Este módulo não ativa coleta, timers, consumidores nem operações paper.

`validate_earnings_component(component, *, decision_at, maturity_at)` retorna
`EarningsPolicyResult`, dataclass frozen com `valid`, `excluded`, `reasons`
(tupla de códigos públicos) e `diagnostics` (tupla de códigos controlados).
Não importa aplicação/configuração, lê arquivos, chama provedores nem abre banco.

O componente tem exatamente nove chaves: `coverage_verified`, `window_start`,
`window_end`, `events`, `source_at`, `available_at`, `policy`, `evidence`, `exclusion`.
A política exige `EXCLUSION_RULE_V1` e o SHA da norma acima. Metadados opcionais
de produtor/versão devem ser strings; `amendment`, quando presente, deve ser
`EMENDA_3_REV3`. Draft, hash ausente e schema legado são recusados.

O módulo valida os fatos normalizados do produtor: datas ISO estritas, contagem
do histórico, último relatório publicado até D−1, hashes dos dois payloads,
consulta cobrindo D−15 a maturidade+15, entradas inválidas, eventos conhecidos,
origem/relógios, classificações e projeção pública. Recalcula a cadência de 91
dias somente na ausência de evento conhecido dentro da tolerância. Compara
classificações, fatos derivados, `coverage_verified` e veredito do produtor com
esse cálculo. A comparação de eventos conserva duplicatas e todos os campos
públicos, admitindo somente diferença de ordem.

DAY/BMO/AMC excluem qualquer data NY entre a entrada e a maturidade, inclusive
as duas fronteiras. Não se deduz execução pontual de BMO/AMC. INSTANT exige
relógio com timezone e data correspondente em Nova York; a comparação temporal
também é inclusiva. Eventos conflitantes permanecem na união conservadora.

`valid=True, excluded=True` representa uma exclusão conhecida coerente; ausência
de dados ou incoerência produz `valid=False, excluded=True`. O contrato de
candidato registra todos os motivos E3 como DATA antes da divisão dos braços
R1. NOT_TRACKED, LAST_REPORT_UNKNOWN, EVIDENCE_INVALID e SOURCE_UNAVAILABLE são
preservados quando os respectivos fatos e veredito são coerentes. Erros brutos
do provedor e identificadores privados não aparecem no resultado.

`event_intersects(event, *, opened_at, maturity_at)` é reutilizável em episódios
vivos. Entrada inválida lança `EarningsPolicyError`, nunca retorna ausência de
interseção. O chamador verifica `available_at <= detection_at`: um anúncio pode
ser observado depois da abertura. A normalização de datas fora de sessão como
DAY depende do calendário fixado pelo chamador; este módulo não consulta nem
inventa um calendário.

Limites de integração:

- `evidence.decision_at` declara a abertura nominal 10:00 NY da sessão. O
  relógio factual do chamador deve pertencer a [10:00,10:01). O produtor não
  precisa adivinhar o microssegundo futuro da leitura. As classificações e o
  veredito de admissão são recalculados usando a fronteira nominal 10:00
  assinada em §3.2/§3.4: INSTANT às 10:00:20 continua EXCLUDES numa leitura às
  10:00:37. O factual verifica causalidade/capture, não desloca essa fronteira.
  Nenhum fato ou veredito é reescrito pelo validador. `evidence.maturity_at`
  coincide com a maturidade derivada do calendário independente fornecido pelo
  contrato de candidato. A interseção da trilha viva usa separadamente o
  `opened_at` real de cada episódio (§3.6).
- O shape do produtor #385 observado no head `5830c3e` ainda contém título draft
  e `amendment_sha=None`; esses bytes são deliberadamente recusados.
- Hash sintaticamente válido não prova retenção, autenticidade ou completude
  do payload. O shape traz a data normalizada do último relatório publicado,
  sem a entrada original de EPS nem recibos completos por fonte. Este helper
  não comprova independentemente esse conteúdo ausente. O produtor auditado e
  a cadeia externa de bytes/recibos permanecem responsáveis por essa ligação.
- Nenhuma resposta vazia isolada implica cobertura negativa. Uma lista de
  eventos vazia pode ser aceita apenas com os três fatos normalizados válidos,
  conforme a flexibilização expressa da Emenda 3; não certifica completude do feed.

Testes usam apenas fixtures sintéticas. Nenhum outcome, estudo, provider ou dado
de produção é executado para validar este módulo.
