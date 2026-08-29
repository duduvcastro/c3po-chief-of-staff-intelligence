# C3PO_WATCH_ALERTS_NTFY_V1 — alertas no Apple Watch via ntfy self-hosted

**Data:** 29/08/2026 · **Autor:** Fable · **Ordem do dono:** "Sim, o Apple Watch é o que mais
importa para mim" (29/08, após prova empírica de que o iOS não espelha web push no watchOS:
C3PO ausente da lista de espelhamento + teste com iPhone bloqueado entregue no iPhone e mudo
no pulso).

## Objetivo

Fazer os alertas do C3PO chegarem ao Apple Watch. Mecanismo: servidor **ntfy** self-hosted no
nosso Lightsail + **app nativo ntfy no iPhone** assinando nosso tópico — notificação de app
nativo espelha no watchOS normalmente. O canal web push existente permanece intocado.

## Arquitetura (v1, mínima)

1. **Serviço novo no compose**: imagem oficial `binwiederhier/ntfy` **pinada por digest
   sha256** (rito da casa), config em arquivo versionado no repo, dados em volume próprio.
2. **Exposição**: subdomínio dedicado atrás da Cloudflare (sugestão: `ntfy.eduardocastro.com.br`),
   server block no nginx do host → contêiner. Nenhuma porta nova exposta diretamente.
3. **Autenticação fail-closed**: `auth-default-access: deny-all`; **token write-only** para o
   backend (publicar) e **token read-only** para os aparelhos do Dudu (assinar). Tokens só em
   secrets, entregues pelo pipeline (padrão umask 077 da #291). Tópico com sufixo aleatório
   não-adivinhável.
4. **Canal no notificador**: `notify()` ganha um segundo envio best-effort — POST ao ntfy com
   timeout curto (≤3s) — DEPOIS do web push, sob a MESMA idempotência por `event_key` já
   existente (DB). Falha do ntfy jamais afeta job, trading ou o canal web push (invariante da
   spec-mãe, inegociável). Categorias: as mesmas 8, filtradas por env
   `ntfy_categories` (default: todas).
5. **Corpo**: as mesmas regras de conteúdo não-sensível já vigentes (EMENDAS 1–2). Nada novo
   viaja que já não viaje pelo web push.

## Nuance de plataforma declarada ANTES do GO (transparência)

Para entrega **instantânea** no iOS, o ntfy self-hosted usa `upstream-base-url: https://ntfy.sh`:
a cada publicação, um **ping de despertar** (URL do servidor + nome do tópico, **sem corpo da
mensagem**) transita pela infraestrutura do ntfy.sh/APNs; o app então busca o conteúdo no NOSSO
servidor. Alternativa sem upstream = entrega com atraso de polling (inaceitável para alertas).
**Proposta v1: aceitar o ping de despertar**, mitigado por tópico não-adivinhável + auth
deny-all (o ping não dá acesso a nada). Se a mesa recusar, a obra para aqui.

## Operação

- Atualização de imagem: manual-only, mesmo rito do installer (#273); sem watchtower.
- Healthcheck do contêiner no compose + sonda leve no system-health (com timeout individual,
  lição Leah); queda do ntfy = card âmbar, nunca vermelho de trading.
- Runbook: provisionar tokens, assinar tópico no app ntfy (iPhone e, se quiser, iPad), ligar
  espelhamento do ntfy no Watch (app nativo aparece na lista normalmente).

## Aceite (fatos, não promessas)

1. Teste disparado pelo C3PO chega ao **Apple Watch** (vibração no pulso, iPhone bloqueado);
2. Derrubar o contêiner ntfy e disparar alertas: jobs e web push seguem intactos (prova de
   best-effort);
3. Publicação sem token é recusada (prova do deny-all);
4. Suíte completa + 5 portões; auditoria cruzada (implementa Codex, audita Fable — o Codex tem
   as mãos do host para DNS/nginx/secrets).

## Assinaturas

- **Dudu:** ASSINADO — 29/08/2026 (ordem expressa citada acima; prioridade máxima = Watch).
- **Fable:** ASSINADO — 29/08/2026 (autor da spec).
- **Codex:** pendente (GO técnico — incluindo o aceite explícito da nuance do ping de
  despertar — + implementação).
