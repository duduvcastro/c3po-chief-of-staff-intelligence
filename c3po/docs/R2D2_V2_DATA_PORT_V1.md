# R2D2 V2 — contrato da porta de dados por arquivos, V1

Esta porta é uma interface privada de evidência, implementada em
[`r2d2_v2_sources.py`](../backend/app/r2d2_v2_sources.py). O mapeamento e o
congelamento pertencem a [`r2d2_v2_shadow.py`](../backend/app/r2d2_v2_shadow.py),
e a interpretação econômica a [`r2d2_v2_contract.py`](../backend/app/r2d2_v2_contract.py)
e [`r2d2_v2_portfolio.py`](../backend/app/r2d2_v2_portfolio.py).
O manifesto documental é `01d258903c060660a51ad48e7506903d038b0fa6901142456e06c7858350c359`.

O código não inclui produtor de mercado auditado, publicação de arquivos, ACK,
rotação automática ou autorização de ativação. `capabilities()` mantém
`production_ready=false` e três contratos de produtor pendentes:

1. Universo completo e verificável às 10:00 ET, com bid/ask causais de idade ≤10 s.
2. Exatas 61 barras diárias OHLCV de sessões oficiais, em unidades históricas sem
   ajuste, cobertura de splits conhecidos e insumos suficientes para ADV20/ATR14.
3. Calendário de earnings com cobertura verificável até o vencimento, incluindo
   uma resposta negativa explícita quando não houver anúncio no intervalo.

`ExistingAppInventory(database).read(now)` lê apenas os snapshots já persistidos
`valuation_universe/NASDAQ_UNIVERSE` e `valuation_universe/NYSE_UNIVERSE`.
Seu resultado é `DIAGNOSTIC_ONLY`, sempre com `coverage_verified=false`.
Não chama screeners, provedores ou o motor V1. Esse inventário não satisfaz os
três contratos acima. As flags de cobertura são afirmações de um produtor a
ser auditado; o parser não certifica sua veracidade nem sua licença de dados.

## Armazenamento e publicação

A raiz é exclusiva da época de coleta e configurada pelo operador. O esquema de
arquivos não contém uma chave `epoch`; portanto, misturar épocas numa raiz não
é um mecanismo suportado de migração de dados.

```text
<raiz-privada-da-epoca>/
  snapshot.json
  events/
    <event_id>.<self_sha256>.json
```

Diretórios privados devem usar `0700` e arquivos `0600`; a leitura rejeita
permissões de grupo/outros. Não são seguidos symlinks na raiz, em seus ancestrais,
no diretório de eventos ou nos arquivos. Os arquivos precisam ser regulares e
permanecer com a mesma identidade, tamanho e timestamps durante a leitura.

O produtor escreve um arquivo temporário privado no mesmo diretório, conclui a
serialização, faz `fsync` do arquivo, publica com rename atômico e sincroniza o
diretório para a durabilidade necessária. `snapshot.json` é substituível; cada
arquivo final de evento é imutável. Publicar um evento deve preservar a
exclusividade do nome, sem sobrescrever um recibo existente. Arquivos temporários
ocultos não são interpretados como eventos concluídos.

Limites da implementação:

| Objeto | Limite |
| --- | ---: |
| `snapshot.json` | 64 MiB |
| Instrumentos no universo | 10.000 |
| Cada evento | 64 KiB |
| Entradas em `events/`, incluindo temporários | 4.096 |

A enumeração é limitada; exceder o limite bloqueia a fita completa de eventos.
A aplicação não instala um produtor, agendador ou processo de limpeza dessa raiz.

## Envelope comum e integridade

Todos os campos abaixo são obrigatórios. O envelope aceita exatamente esses
campos mais `universe` no snapshot ou `event_id` e `event` no evento.

| Campo | Contrato |
| --- | --- |
| `schema` | `V2_SHADOW_SOURCE_SNAPSHOT_V1` ou `V2_SHADOW_SOURCE_EVENT_V1` |
| `manifest_sha` | O SHA integral do manifesto acima |
| `source_id` | Identidade estável do produtor; token de até 96 caracteres |
| `provenance` | Exatamente `producer`, `version`, `payload_sha256` |
| `source_at` | Timestamp da evidência de origem, com timezone explícito |
| `available_at` | Timestamp em que o produtor teve essa evidência disponível |
| `sequence` | Inteiro não negativo; `bool` não é inteiro válido |
| `self_sha256` | SHA256 canônico do envelope sem este campo |

`producer`, `version`, `source_id`, `event_id`, `instrument_key`, `entitlement_id`
e `reason` usam `[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}` quando presentes. Hashes são
64 dígitos hexadecimais minúsculos. JSON com chaves duplicadas, NaN ou infinito é
rejeitado; strings numéricas e booleanos não substituem preços ou scores.

Canonicalização exata em Python; não é uma alegação de conformidade RFC 8785:

```python
body = {key: value for key, value in envelope.items() if key != "self_sha256"}
wire = json.dumps(body, sort_keys=True, separators=(",", ":"),
                  ensure_ascii=True, allow_nan=False).encode()
envelope["self_sha256"] = hashlib.sha256(wire).hexdigest()
```

`provenance.payload_sha256` referencia os bytes de evidência de origem definidos
pelo produtor e sua auditoria. A porta valida seu formato; não busca nem
recalcula esse objeto externo. `self_sha256` detecta alteração do envelope,
mas não autentica um produtor. O leitor também calcula `envelope_sha256` dos
bytes efetivos do arquivo, incluindo sua serialização. Republicar o mesmo
`event_id` com outros bytes, mesmo apenas reformatando JSON, é conflito.

A cadeia temporal do envelope é `source_at <= available_at <= now`.
Timestamps não são inferidos de data da sessão, mtime, momento de leitura ou
outro campo. Um envelope com schema/hash/causalidade inválidos gera diagnóstico
`MISSING`, sem promover seu universo como confiável.

## Snapshot e instrumento

`universe` contém exatamente `coverage_verified` e `instruments`. A lista precisa
representar o universo declarado por completo, incluindo instrumentos cujas
respostas estejam pendentes ou sejam inválidas. Símbolos são únicos no universo
e usam `[A-Z0-9][A-Z0-9.-]{0,19}`. O coletor identifica o instrumento por
`US:<symbol>`; `market` continua dado de classificação, sem criar uma segunda
entrada quando a bolsa reportada muda.

Exemplo **PRIVATE / SYNTHETIC** com hash correto e cobertura deliberadamente não
verificada. Este envelope deve resultar em `MISSING`; não é um universo vazio
certificado. Os nomes, preços e recibos desta página são exclusivamente sintéticos.

```json
{
  "schema": "V2_SHADOW_SOURCE_SNAPSHOT_V1",
  "manifest_sha": "01d258903c060660a51ad48e7506903d038b0fa6901142456e06c7858350c359",
  "source_id": "synthetic-producer-v1",
  "provenance": {
    "producer": "synthetic",
    "version": "fixture-v1",
    "payload_sha256": "7b67c431170dd07da0bdc9f65f723188d654cb88471c62e60d3e04c06ecf2efb"
  },
  "source_at": "2026-09-08T14:00:00+00:00",
  "available_at": "2026-09-08T14:00:01+00:00",
  "sequence": 0,
  "universe": {
    "coverage_verified": false,
    "instruments": []
  },
  "self_sha256": "01c63c875fba865b88618291152eecf574fcb9e1046681594828d721d34ca9fc"
}
```

Cada elemento de `instruments` contém exatamente os campos mostrados neste
fragmento **PRIVATE / SYNTHETIC**. As respostas abaixo estão completas quanto ao
seu recebimento, mas deliberadamente sem dados válidos de risco/barras/earnings.
Não constituem um candidato elegível.

```json
{
  "symbol": "SYNTHETIC",
  "market": "NASDAQ",
  "security_type": "COMMON_STOCK",
  "classification_verified": true,
  "sequence": 0,
  "source_at": "2026-09-08T14:00:00+00:00",
  "available_at": "2026-09-08T14:00:00+00:00",
  "quote": {
    "bid": 99.95,
    "ask": 100.05,
    "bid_source_at": "2026-09-08T14:00:00+00:00",
    "ask_source_at": "2026-09-08T14:00:00+00:00",
    "available_at": "2026-09-08T14:00:00+00:00"
  },
  "daily": {
    "bars": [],
    "splits": [],
    "adjustment": "RAW_UNADJUSTED",
    "coverage_verified": false,
    "split_coverage_verified": false,
    "source_at": "2026-09-08T14:00:00+00:00",
    "available_at": "2026-09-08T14:00:00+00:00"
  },
  "risk": {
    "value": null,
    "producer": "synthetic-risk",
    "source_at": "2026-09-08T14:00:00+00:00",
    "available_at": "2026-09-08T14:00:00+00:00"
  },
  "earnings": {
    "coverage_verified": false,
    "window_start": "2026-09-08T14:00:00+00:00",
    "window_end": "2026-09-21T19:55:00+00:00",
    "events": [],
    "source_at": "2026-09-08T14:00:00+00:00",
    "available_at": "2026-09-08T14:00:00+00:00"
  }
}
```

| Componente | Conteúdo e condições |
| --- | --- |
| Identidade | `symbol`, `market` (`NYSE`/`NASDAQ`), `security_type`, `classification_verified` explícito, `sequence`, `source_at`, `available_at` |
| `quote` | Exatamente `bid`, `ask`, `bid_source_at`, `ask_source_at`, `available_at`; preços positivos, `bid <= ask`; cada relógio de origem ≤ recebimento e idade ≤10 s na decisão |
| `daily` | Exatamente `bars`, `splits`, `adjustment`, `coverage_verified`, `split_coverage_verified`, `source_at`, `available_at` |
| `risk` | Exatamente `value`, `producer`, `source_at`, `available_at`; score numérico nativo finito em [0,100] para ser válido; resposta `null` preservada como inválida |
| `earnings` | Exatamente `coverage_verified`, `window_start`, `window_end`, `events`, `source_at`, `available_at`; cada evento tem `event_at` e `available_at` |

O manifesto admite `COMMON_STOCK` e `COMMON_STOCK_ADR`; uma classificação
verificada diferente é avaliada explicitamente pelo contrato. Uma resposta
inválida não é normalizada para a classe admitida nem seu score é corrigido.

`daily.adjustment` deve ser `RAW_UNADJUSTED`. Há exatamente 61 barras, ordenadas
pelas 61 sessões oficiais anteriores à entrada. O mapper usa XNYS de
`exchange_calendars`, registra a versão/hash do calendário e não completa a
sequência por aproximação de dias úteis. Uma barra tem exatamente esta forma:

```json
{
  "session_date": "2026-09-04",
  "open": 100.0,
  "high": 101.0,
  "low": 99.0,
  "close": 100.0,
  "volume": 150000.0,
  "source_at": "2026-09-04T20:00:00+00:00",
  "available_at": "2026-09-04T20:00:01+00:00",
  "complete": true,
  "regular_session": true
}
```

`complete` e `regular_session` devem estar presentes e verdadeiros para a barra
ser válida. OHLC deve ser finito, positivo e ordenado; volume deve ser finito e
não negativo. Os valores brutos são preservados. O port não calcula OHLC a partir
de close/volume, não completa barras ausentes nem transforma ausência em zero.

Cada split contém exatamente estes campos; `factor` é novas ações/ações antigas:

```json
{
  "factor": 2.0,
  "effective_at": "2026-09-08T13:30:00+00:00",
  "source_at": "2026-09-03T12:00:00+00:00",
  "available_at": "2026-09-03T12:00:01+00:00"
}
```

O timestamp `source_at` do split é independente de `effective_at` e não pode ser
inventado a partir dele. Splits conhecidos com efetivação futura são preservados;
o contrato aplica somente os já efetivos na decisão. `splits=[]` só representa
uma ausência verificada quando `split_coverage_verified=true` e a cobertura foi
auditada. ATR14 usa o histórico ajustado apenas pelos splits conhecidos/efetivos;
ADV20 usa `close * volume` bruto, sem ajuste redundante de volume.

Em earnings, `events=[]` não prova ausência de anúncios por si só. A cobertura
precisa ser verdadeira e abranger o instante da decisão até exatamente o
vencimento (fechamento oficial da décima sessão menos cinco minutos). Não se
amplia um timestamp parcial para o dia inteiro. Um limite final um microssegundo
antes do vencimento é insuficiente. Eventos conhecidos na decisão ou exatamente
no vencimento pertencem ao intervalo de exclusão; um evento depois dele não
pertence. Cada `available_at` individual precisa ser causal, além do recibo do
calendário completo. Datas sem horário não devem receber um horário inventado:
a V1 da porta requer `event_at` explícito; qualquer futura extensão precisará
distinguir a granularidade da fonte.

### Completo, inválido e ainda ausente

O retorno `V2_SHADOW_SOURCE_BATCH_V1` acrescenta recibos, `status` e `diagnostics`.
Cada instrumento reconhecido preserva seu payload bruto completo, mesmo inválido,
com `data_available=false` e códigos diagnósticos. Esses campos derivados não
são campos do envelope produzido.

`data_available` não substitui `input_complete`. O mapper preserva os metadados
de resposta e registra `source_issues`: por exemplo, risco `null` já respondido
congela o primeiro snapshot como `DATA_INELIGIBLE`; uma resposta posterior melhor
não o substitui. Bid/ask ainda ausentes permanecem pendentes até a janela fechar.
Cobertura diária falsa e disponibilidade futura de earnings não são convertidas
em `ELIGIBLE` apenas porque os outros campos estão preenchidos. O fechamento de
captura é exclusivo em 10:01 ET e conserva as lacunas como dados inelegíveis.

## Eventos de preço e corporativos

Os arquivos têm o nome exato `event_id.self_sha256.json`. O corpo `event` contém
`type`, `at`, `available_at`, `session` e, salvo eventos de relógio, `instrument_key`.
Para o coletor atual, use `US:<symbol>`. `session` é a sessão de processamento,
separada do instante de origem. A porta não cria eventos a partir de uma cotação
isolada nem converte anúncio de dividendo em direito econômico.

Exemplo **PRIVATE / SYNTHETIC**, com hash correto. Seu nome seria
`fixture-trade-0000.9761fab934438f552648333911de8309c696863d26b2b1ae6c71364adaa3c9b9.json`.

```json
{
  "schema": "V2_SHADOW_SOURCE_EVENT_V1",
  "manifest_sha": "01d258903c060660a51ad48e7506903d038b0fa6901142456e06c7858350c359",
  "source_id": "synthetic-producer-v1",
  "provenance": {
    "producer": "synthetic",
    "version": "fixture-v1",
    "payload_sha256": "0d763b34812b92ffc7d834ae18780c3f287ac4c2bca0ee0fb577839c8d9133ee"
  },
  "source_at": "2026-09-08T14:00:00+00:00",
  "available_at": "2026-09-08T14:00:01+00:00",
  "sequence": 0,
  "event_id": "fixture-trade-0000",
  "event": {
    "type": "TRADE",
    "at": "2026-09-08T14:00:00+00:00",
    "available_at": "2026-09-08T14:00:00+00:00",
    "session": "2026-09-08",
    "instrument_key": "US:SYNTHETIC",
    "price": 100.0,
    "regular": true
  },
  "self_sha256": "9761fab934438f552648333911de8309c696863d26b2b1ae6c71364adaa3c9b9"
}
```

A porta retorna o corpo preservado, mais `event_id`, `source_id`, `source_at`,
`envelope_available_at`, `sequence`, `provenance`, `manifest_sha`, `self_sha256` e
`envelope_sha256`. O `available_at` do evento não é sobrescrito pelo recibo do
envelope. Ao aplicar a evidência, o coletor conserva a disponibilidade da fonte
como `source_available_at` e registra como disponibilidade do motor o instante
real da leitura. Não retroage conhecimento após downtime.

| `type` | Campos adicionais obrigatórios | Semântica |
| --- | --- | --- |
| `TRADE` | `price`, `regular` | Trade observado; `regular` booleano explícito |
| `MARK` | `price`, `regular` | Marcação explícita; não substitui evidência de execução |
| `QUOTE` | `bid`, `ask`, `bid_at`, `ask_at`, `regular` | Cotação com relógios próprios, sem cruzamento |
| `BAR` | `end_at`, `open`, `high`, `low`, `close`, `regular`, `coverage_complete` | Intervalo completo `at < end_at <= available_at`; OHLC válido |
| `DATA_GAP` | `reason` | Lacuna explícita; não significa retorno zero |
| `SPLIT` | `factor` | `at` é o instante efetivo; fator positivo |
| `DIVIDEND_ENTITLEMENT` | `entitlement_id`, `net_per_share` | Direito econômico por ação; `null` registra valor líquido não observável |
| `DIVIDEND_PAYMENT` | `entitlement_id` | Pagamento de direito identificado, sem criar um segundo dividendo |
| `EARNINGS` | `earnings_at` | Evidência de anúncio; horário do anúncio pode ser futuro |

`BAR` admite opcionalmente `trades`, lista completa de objetos com exatamente
`at` e `price`, ordenados dentro de `[at, end_at)`. Não há reconstrução de ordem
intrabar a partir de OHLC. Uma lista inexistente não é uma lista vazia de trades.
`coverage_complete=false` é um evento válido de lacuna observacional; deve
chegar ao ledger, não desaparecer da fita. Preços são finitos e positivos;
`net_per_share`, quando conhecido, é finito e não negativo. Não existem os tipos
genéricos `PRICE` ou `DIVIDEND`.

A API pura também reconhece `MATURITY`, `SESSION_OPEN` e `SESSION_CLOSE`.
Eles não têm campos adicionais; os dois últimos não usam `instrument_key`.
**O produtor de arquivos do coletor atual não está autorizado a emitir esses três
tipos:** sua agenda pertence ao calendário do coletor. Um evento externo assim
gera `SOURCE_CLOCK_EVENT_NOT_AUTHORIZED`, em vez de duplicar a agenda oficial.

### Sequência, replay e retenção

No fluxo de eventos de cada `source_id`, `sequence` começa em **0** e é contíguo
(0,1,2,...). Não reinicia durante a época, inclusive após reinício de processo.
Essa contagem é independente do contador de snapshots e do contador por
instrumento. O coletor verifica a continuidade por produtor antes de ordenar os
eventos para aplicação econômica. Buracos não são considerados ausência de trades.

`event_id` identifica um payload imutável; o mesmo ID com recibo diferente é
conflito. A porta pode devolver novamente todos os eventos presentes. Seu cache
em memória não é o registro durável: o store do coletor persiste estado, sequência,
recibos e journal com hash, atomicamente, para suportar replay após restart.

Não existe ACK ao produtor, watermark de remoção, exportador de confirmações ou
rotação implementada nesta porta. **Nenhum arquivo pode ser removido por idade,
mtime ou sucesso de leitura apenas.** Antes de qualquer futura rotação, o produtor
precisa de mecanismo auditado que confirme no store durável a incorporação exata
por época, `event_id`, SHA e sequência, preserve as evidências arquivadas e permita
replay. Sem isso, atingir 4.096 entradas bloqueia a fita; não autoriza apagar dados.

Falha de um evento (arquivo/hash/causalidade/shape/ID) faz `events(now)` devolver
lista vazia e `last_event_diagnostics` não vazio, sem disponibilizar uma fita
parcial como completa. O consumidor deve distinguir esse caso de uma lista vazia
sem erros e manter os diagnósticos de vivacidade/continuidade. Um diretório vazio
não certifica cobertura de mercado.

## Verificação local e limite de ativação

Os testes sintéticos de `test_r2d2_v2_sources.py` cobrem isolamento de paths,
permissões, tamanho, integridade, campos inválidos preservados, causalidade e
replay. `test_r2d2_v2_source_mapping.py` exercita o caminho real de arquivos até o
mapper e o coletor `DIAGNOSTIC`, com calendário oficial instalado, feriados,
fechamento antecipado, bordas temporais e ausência de chamadas ao ledger.

Uma instância `DIAGNOSTIC` registra dados e motivos em época separada, sem carteira,
coorte de certificação ou ordens. O código da porta, os exemplos desta página e os
testes não são release, certificação de provedor, resultado de calibração nem GO
de coleta. O modo certificado continua dependente da liberação nominal, da
calibração aceita e das fontes auditadas, conforme o contrato principal do gerador.
