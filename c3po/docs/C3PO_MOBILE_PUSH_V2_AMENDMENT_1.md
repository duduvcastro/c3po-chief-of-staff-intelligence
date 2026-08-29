# C3PO_MOBILE_PUSH_V2 — EMENDA 1: três categorias novas por ordem do Dudu

**Data:** 28/08/2026 · **Spec emendada:** `C3PO_MOBILE_PUSH_V2.md` (sha `901971e5…bc4fa`).
Esta emenda exerce a cláusula "inclusão futura só por emenda" do catálogo v1.

## Categorias adicionadas (todas opt-in, no painel de alertas)

1. **`security_login`** — login bem-sucedido no C3PO. Corpo não-sensível (hora + rótulo genérico
   do dispositivo; nunca IP ou dado de conta — push viaja fora da auth). `event_key` por sessão.
   Consenso das três mãos.

2. **`sell_win`** — episódio encerrado com resultado LÍQUIDO positivo. **Unidade = episódio,
   nunca perna** (coerente com o win rate oficial; evita a inflação por fatiamento que a mesa
   já documentou no caso DINO). Corpo: símbolo + resultado líquido do episódio. `event_key` por
   episódio.
   **Voto contrário do Fable, registrado**: reforço seletivo de vitórias distorce a intuição do
   operador (11 silêncios para cada 4 sinos, na sessão típica); colide com a lição do Painel I.
   Ordem expressa do Dudu prevalece — a máquina é dele; a divergência fica na história.

3. **`hourly_win_rate`** — a cada hora cheia, SOMENTE com pregão US aberto (10:30–17:00 BRT em
   dia útil de NYSE/NASDAQ): % de episódios positivos da sessão até ali, no formato do painel
   ("W/fechados = Z%"). Sem episódios fechados no dia → sem envio (silêncio > ruído vazio).
   `event_key` por hora. Ressalva branda do Fable (frequência de estímulo intradiário), sem
   voto contrário: a métrica é simétrica e honesta.

## Invariantes preservados (da spec-mãe, inegociáveis)

Best-effort com timeout curto; falha de push jamais afeta job ou trading; conteúdo entregue
fora da auth permanece não-sensível; opt-in individual; contadores idênticos aos dos painéis
oficiais (mesma fonte, nunca cálculo paralelo).

## Assinaturas

- **Dudu:** ASSINADO — 28/08/2026 (ordem expressa das categorias 2 e 3 após conselho contrário
  ouvido; categoria 1 pedida em mensagem anterior).
- **Fable:** ASSINADO — 28/08/2026 (com voto contrário à categoria 2 e ressalva à 3, registrados).
- **Codex:** pendente (GO técnico + implementação + auditoria cruzada do Fable na PR).
