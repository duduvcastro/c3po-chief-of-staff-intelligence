# C3PO_WATCH_NATIVE_APP_V1 — alertas nativos e independentes no Apple Watch

**Data:** 29/08/2026 · **Autor:** Fable · **Antecessora:** `C3PO_WATCH_ALERTS_NTFY_V1` (arquivada
registrada-não-construída, sha final `d413e0a8…`). **Ordem do dono:** "so o nativo" — meta é
independência total do iPhone ("Isso é o q eu mais queria") + complication no mostrador.
**Pré-requisito em andamento:** conta Apple Developer BR do Dudu (Individual; inscrição
submetida 29/08, aguardando aprovação da Apple).

## Objetivo

App **watchOS standalone** que recebe push direto via APNs — o Watch com Wi-Fi/LTE notifica
com o iPhone desligado, distante ou em casa — e exibe uma **complication** com a métrica da
sessão no mostrador.

## Desenho

1. **App** (SwiftUI, watchOS 10+; stub iOS mínimo apenas se a distribuição exigir), em
   `c3po/watch/` no repo. **Invólucro NEUTRO**: nome provisório "EC Ops" (Dudu batiza),
   ícone sóbrio, **ZERO marcas Star Wars em nome/ícone/strings/metadados do bundle** —
   pinado por teste no repo (varredura de Info.plist/assets/strings). Todo o tema vive no
   conteúdo servido pelo backend, fora do alcance de qualquer revisão da Apple.
2. **Push**: emissor APNs no backend (HTTP/2, JWT com chave `.p8`) — chave e ids APENAS em
   secrets, entregues pelo pipeline (padrão umask 077 da #291); jamais no repo.
3. **Registro de aparelho**: o app chama `POST /api/v1/watch/register` com o device token,
   autenticado por **token dedicado de aparelho** (`watch_device_token`) emitido no painel
   (owner-only), hasheado at rest, revogável — o relógio não vive de sessão de 30 minutos.
4. **Canal no notificador**: segundo envio ativo em `notify()` (junto ao web push), best-effort
   ≤3s, sob a MESMA idempotência por `event_key`, mesmas 8 categorias com opt-in por aparelho;
   corpos idênticos aos atuais (regras das EMENDAS 1–2 valem intactas). Falha de APNs jamais
   afeta job, trading ou o canal web push.
5. **Complication**: formato do painel oficial ("4W/15 · 26,7%"), fonte ÚNICA =
   `episode_summary` (a caminhada do Falcon — regra DINO, nunca cálculo paralelo). Atualização
   por push de complication respeitando o orçamento (~50/dia): hora cheia em pregão aberto +
   fechamento; fallback de refresh agendado do próprio watchOS.
6. **Distribuição privada, nunca App Store pública/externa**: primária = instalação de
   desenvolvimento pelo Xcode do Mac do Dudu (conta BR assina; perfis de 1 ano; aparelhos por
   UDID — independe do Apple ID logado nos aparelhos); secundária = TestFlight interno se a
   conta Individual comportar. Builds/assinaturas executados pelo Dudu com runbook mastigado
   (Xcode Cloud gratuito fica registrado como automação futura opcional).

## Invariantes (da spec-mãe de push, inegociáveis)

Best-effort com timeout curto; conteúdo entregue fora da auth permanece não-sensível; opt-in
individual; contadores idênticos aos painéis oficiais; segredos nunca no repo; imagem/tema da
casa jamais nos metadados do bundle.

## Aceite (fatos, não promessas)

1. Push chega ao Watch com o **iPhone DESLIGADO** (a prova da independência — o ponto da obra);
2. Complication exibe e atualiza a métrica da sessão em pregão;
3. Derrubar o emissor APNs (chave inválida): jobs, trading e web push seguem intactos;
4. Teste de metadados: nenhuma marca no bundle;
5. Suíte completa + 5 portões + auditoria cruzada (implementa Codex — backend APNs/registro e
   app —, audita Fable; passos de build no Mac executados pelo Dudu com runbook).

## Assinaturas

- **Dudu:** ASSINADO — 29/08/2026 ("so o nativo"; prioridade máxima declarada).
- **Fable:** ASSINADO — 29/08/2026 (autor da spec).
- **Codex:** pendente (GO técnico + implementação; GO pode sair antes da aprovação da Apple —
  só a instalação no aparelho espera a conta).
