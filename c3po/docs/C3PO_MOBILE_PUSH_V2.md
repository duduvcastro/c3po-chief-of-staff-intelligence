# C3PO_MOBILE_PUSH_V2 — alertas operacionais no iPhone (Fase 2 da PWA)

**Data:** 28/08/2026 · **Autor:** Fable · **Pré-requisito cumprido:** PWA instalada e aceita
pelo Dudu no aparelho (C3PO_MOBILE_PWA_V1, sha `93c2972b…`).

## 1. Entrega ao usuário

- Botão **"Ativar alertas"** na área de configurações do painel (visível só na PWA instalada);
  toque → permissão do iOS → inscrição registrada. Toggles por categoria, todos opt-in;
- Notificações nativas (tela bloqueada, som, badge) com o app fechado; tocar abre o painel
  relevante (deep link por categoria).

## 2. Catálogo v1 — operacional, nunca ansiedade

1. `kill_criterion` — tripwire M3 / veredictos de leitura (15ª/20ª) publicados;
2. `job_failure` — falha dos jobs críticos (backup, cash yield, estudo, censo, atestado de
   governança) — emitida nos MESMOS pontos que hoje pingam fail no healthchecks;
3. `governance_critical` — card de Governança mudando para CRITICAL (novo high/critical ou drift);
4. `mesa_reading` — report de leitura da mesa publicado (ex.: 5ª sessão, gate V3).

**Vetado no v1 (registro de mesa):** preço, P&L intradiário, movimento de posição — a classe de
estímulo que o Painel I provou destrutiva não entra pelo bolso. Inclusão futura só por emenda.

## 3. Arquitetura (custo US$ 0, nada de serviço novo)

- **Service worker mínimo, exclusivamente para push** (`push` + `notificationclick`); nenhuma
  interceptação de fetch, **zero cache** — regra de frescor da V1 preservada e testada
  (teste pina que o SW não registra handler de fetch);
- Chaves **VAPID próprias** geradas pelo Codex e guardadas como secret (`.env`), nunca em repo;
- Tabela `push_subscriptions` (append + revogação lógica; endpoint, chaves do browser, usuário,
  categorias, `created_at`) atrás da auth existente; inscrição/desinscrição só autenticada;
- Emissor `push_notify(category, title, body, deep_link)` chamado nos pontos de evento já
  existentes; envio best-effort com timeout curto — **falha de push jamais afeta o job** (mesma
  regra dos pings); log de envio para diagnóstico;
- iOS ≥16.4, PWA instalada; permissão exige gesto do usuário; desinstalar o ícone mata a
  inscrição (re-ativável).

## 4. Aceite (factual, no aparelho do Dudu)

1. Ativar alertas → permissão → inscrição gravada;
2. Notificação de teste disparada pelo Codex chega com app fechado;
3. Toque abre o painel correto;
4. Screenshot da notificação na tela bloqueada = atestado.

## 5. Execução

Spec assinada → implementação Codex (backend+SW) ou dividida com Fable (frontend) conforme
agenda da semana do gate — **prioridade abaixo dos marcos de 1–5/09**, salvo ordem do Dudu.
Auditoria cruzada de praxe; 5 portões.

## Assinaturas

- **Fable:** ASSINADO — 28/08/2026.
- **Dudu:** ASSINADO — 28/08/2026 ("ok" à redação, com a demanda "onde tá isso?" como origem).
- **Codex:** pendente (GO técnico).
