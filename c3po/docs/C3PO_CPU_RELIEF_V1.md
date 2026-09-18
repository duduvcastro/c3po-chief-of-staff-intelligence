# C3PO_CPU_RELIEF_V1 — retirar carga desperdiçada antes de mudar de plano

**Evidência:** laudo de performance `645fe6dd…d247` (5 sessões) e contraprova Lightsail
`bf0751f4…e95bc`: burst zerou em 28/08, 02/09 e 03/09 com a CPU pinada no baseline de 20%.
**Ordem do dono (04/09):** Fable implementa, Codex audita, merge só por autorização nominal,
deploy somente fora do pregão. Duas PRs independentes e reversíveis.

## PR B — polling do painel, cache R2D2 e Leah

### Polling (frontend, `usePanelPolling`)
- mercado aberto + aba visível: frequência atual (`live-positions` 1 s, `/r2d2` 2 s,
  índices 10 s, saúde 60 s);
- aba oculta: polling **suspenso** (timer limpo; nenhuma requisição); aba que nasce oculta
  não carrega nem agenda até ficar visível; após o cleanup do efeito (desmontagem) nada mais
  agenda — nem um fetch que estava em voo;
- mercado fechado + aba visível: intervalo mínimo de **60 s**;
- aba visível de novo: **uma** atualização imediata e um único timer novo (nunca dois).
- A fonte de "mercado aberto" é o campo aditivo `market_session_open` que os payloads
  `/api/v1/r2d2` e `/api/v1/r2d2/live-positions` passam a carregar (calendário XNYS,
  sessão regular). Sem o campo (backend antigo) o frontend assume aberto.

### Cache server-side com single-flight (`app/read_cache.py`)
- Chaves `dashboard` e `live_positions`; TTL **5 s em pregão / 30 s fora**
  (`r2d2_read_cache_open_seconds` / `r2d2_read_cache_closed_seconds`).
- Concorrentes na mesma chave compartilham UMA computação; exceções nunca são cacheadas.
- Cacheia **somente leitura**: nenhuma rota de mutação ou comando passa pelo cache.
- Validade **ancorada no início da computação** (um snapshot nunca é servido além do TTL
  contado do seu instante as-of); `invalidate(chave)` avança a geração DAQUELA chave (invalidar `a` nunca quebra o
  single-flight de `b`); `invalidate()` avança a época global — computação iniciada antes não
  repovoa a chave e chamador posterior nunca coalesce no voo antigo; erro do provedor de TTL derruba o flight e alcança todos os waiters.
- Invalidação explícita (`invalidate`). Limite honesto: os trades acontecem no processo do
  worker, que não alcança o cache do processo da API — o TTL de 5 s em pregão é o teto de
  defasagem de um dashboard lido logo após um trade. Não existem rotas de mutação do R2D2 na
  API hoje; se surgirem, devem chamar `r2d2_read_cache.invalidate()`.

### `POST /api/v1/leah/agent/sync` (`app/leah_sync_guard.py`)
- uma execução simultânea por identidade de dispositivo (concorrentes esperam);
- payload idêntico (fingerprint canônico) dentro de **30 s** devolve o resultado já calculado;
- payload alterado nunca é descartado;
- deadline rígido de **10 s** END-TO-END gravado no próprio voo (`completed_at > deadline_at`
  classifica conclusão tardia de forma atômica; conclusão que pousa na borda do prazo é
  entregue ao chamador, sem 504 nem cooldown) (conta desde a entrada, inclui a espera na fila
  do dispositivo; fila que estoura → 503 + `Retry-After`; execução que estoura → 504); o trabalho em
  curso não é interrompido (interromper no meio de um upsert deixaria estado parcial), mas
  fica registrado como em voo: uma nova tentativa recebe 503 + `Retry-After` em vez de
  iniciar outra execução;
- timeout/erro abrem cooldown para o mesmo fingerprint (429 + `Retry-After`) — sem
  tempestade de retry;
- contadores: `executed` (inclui conclusões tardias, contadas em `late_completions`),
  `deduplicated`, `coalesced` (mesmo payload esperou e reaproveitou) vs `queued` (payload
  distinto esperou), `busy_rejected`, `backoff_rejected`, `timeouts`, `errors`, duração
  média/máxima/última medida no término real do trabalho (`leah_sync_guard.snapshot()` e logs).

### Invariantes
Nenhuma mudança em seleção, sizing, execução, saída, `policy_epoch`, scan, atestado ou
incidente; nenhuma alteração do plano Lightsail; cache nunca cruza usuários (os payloads
cacheados são globais por construção — o dashboard do experimento não tem conteúdo por
usuário).

### Medição pós-deploy
Uma sessão completa com as mesmas seis queries do laudo e os gráficos do Lightsail. Critério
para liberar a Obra B: CPU p95 em pregão < 60%, burst não chega ao piso e fecha ≥ 20%,
duração p95 dos ciclos < 30 s, sem regressão funcional ou aumento de erros.

## PR A — Command Center agregado

- `GET /api/v1/command-center` é estendido **aditivamente**: sem `include`, o contrato é o
  mesmo de sempre; com `?include=a,b,...` (nomes fixos: `alerts`, `navigation_indicators`,
  `system_health`, `reports`, `market_data_providers`, `r2d2`, `markets_live`,
  `markets_index`; nome desconhecido → 422) o payload ganha `sections` + `section_status`.
- As seções rodam **em paralelo** (pool dedicado), chamando os serviços diretamente —
  **nenhuma chamada HTTP interna ao próprio backend**. Uma fonte indisponível fica `null`
  com `section_status[nome] = {status: "error", error}`; o card nunca vira 502 por isso.
- Permissão por seção = a MESMA regra canônica da rota espelhada
  (`access_control.required_permissions`): R2D2 exige `r2d2`, mercados exigem `markets`,
  etc. O agregado jamais entrega o que a rota direta recusaria; sem permissão → `skipped`.
- **Um único prazo por request** (`command_center_section_timeout_seconds`, 8 s, deadline
  absoluto): as seções vivas são submetidas ANTES do grupo cacheável e os dois grupos correm
  em paralelo sob o mesmo prazo; toda espera — inclusive entrar num cálculo cacheável já em
  voo de outro request (`wait_timeout` do single-flight) — gasta só o orçamento restante.
  Fonte pendurada vira `{status: error, error: timeout}` e nunca segura a resposta; trabalho
  ainda enfileirado ao vencer o prazo é cancelado (reauditoria Codex `d960c0d`, P2).
- **Admissão por seção**: no máximo UM produtor em voo por seção (semáforo por nome); uma fonte
  travada ocupa um slot e um worker, nunca o pool — seções saudáveis continuam respondendo.
- **Seções vivas fora do cache do agregado** (`r2d2`, `markets_live`, `markets_index`): resolvidas
  a cada chamada pelos seus próprios caches — o agregado nunca fica mais velho que a rota direta
  (teto de 5 s do R2D2 preservado).
- **Renovação da sessão na abertura**: o `GET /auth/session` do boot renova a janela de inatividade
  para TODO perfil; o agregado não renova mais nada; o mount do frontend não dispara heartbeat.
- Erros são **redigidos**: cliente e log recebem só o nome da classe da exceção.
- Chave de cache canônica (seções ordenadas) e **limitada** (`command_center_cache_max_entries`,
  256; expirados expurgados primeiro, depois os de vencimento mais próximo).
- Cache server-side de **10 s** (`command_center_cache_seconds`), single-flight, **segregado
  por usuário e conjunto de permissões** (chave = e-mail + permissões + seções pedidas).
  A seção `r2d2` reutiliza o cache da PR B.
- Frontend: a abertura do Command Center passa a fazer **uma** requisição agregada, distribui
  o conteúdo (relatórios, provedores, saúde, contador de alertas, indicadores) e **semeia** a
  Millennium Falcon (R2D2, índices, saúde), que só volta a consultar a API no seu próximo
  ciclo de polling (`initialLoad: false`). Conteúdo e estados atuais preservados.
- **Contrato de abertura**: no máximo **quatro** chamadas — `auth/session`, o agregado,
  `r2d2/live-positions` e o POST de telemetria de page-load. O heartbeat só dispara por
  atividade real posterior (o primeiro fica para o intervalo regular); `navigation-seen`
  só por navegação. Limite honesto: sem harness JS no repo, a contagem é pinada por
  contrato estático — uma medição comportamental exige o rastreador de page-load em
  produção (`request_count` por abertura), que é exatamente a métrica pós-deploy.
- Dependência declarada: esta PR é **empilhada** sobre a PR B (reutiliza `read_cache` e
  `usePanelPolling`); merge B → A; cada uma reversível por si.
