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
