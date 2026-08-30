# R2D2_SHADOW_CANDIDATE_LOG_V1 — o custo do que recusamos

**Data:** 29/08/2026 · **Autor:** Fable · **Ordem do dono:** "Vamos começar pelo 1" (29/08),
sobre a tese: o funil rejeita centenas de candidatos por sessão sem registrar o desfecho
contrafactual — sabemos o resultado do que compramos, não o custo do que recusamos.
Herdeira direta: linha #10 do ledger (counters do funil), probe H3-camada-1 (rota provisória
disparou ZERO em 425 episódios — funil largo é letra morta) e o cascade de ~20 degraus do
Entregável 0.

## Objetivo

Registrar, por sessão e por candidato, **cada decisão do funil** (aceito ou rejeitado, com o
degrau e os insumos point-in-time) e computar para TODOS o **mesmo desfecho ±1R líquido de
fricção do ENTRY_QUALITY_STUDY_V1** — tornando populações aceita e rejeitada comparáveis com
uma régua única já assinada.

## Desenho

1. **Registro no ponto de decisão** (append-only, point-in-time): sessão, timestamp UTC,
   símbolo/mercado, `policy_epoch`, degrau alcançado no cascade + razão de rejeição (id do
   degrau), insumos no instante (score/composite, cotação as-of), e o **split
   qualidade×capacidade** (rejeitado por critério ou por cota cheia — a distinção que decide a
   V2). Aceitos entram no MESMO esquema com flag e link ao trade — uma população, uma régua.
2. **Desfecho contrafactual** (job noturno pós-fechamento): fill sintético no sinal + fricção
   real (`_paper_exit_execution`), barreira ±1R até o fechamento da sessão, 4 categorias,
   censura nos termos das Atestações 1–2 do estudo de entrada (`bar_unavailable` = cobertura,
   nunca violação). **Reuso do runner existente — nenhum estimador novo, nenhuma régua
   paralela.**
3. **Evidência**: tabela própria + JSONL diário hasheado (sha256), emitido como
   `ledger_candidate_lines` com `ledger_admission_authorized=false` (mecanismo da #275) —
   admissão ao ledger canônico permanece humana. Retenção alinhada ao draft
   DISK_RETENTION_AND_OFFLOAD_V1 (offload B2 quando assinado).
4. **Invariante READ-ONLY absoluto**: o logger observa o funil e JAMAIS o influencia — caminho
   quente ganha só serialização; **teste-pino de equivalência**: plan/execute byte-idênticos
   com logger ligado e desligado.
5. **Custo declarado**: universo ~700 candidatos/dia → ~700 linhas/sessão + desfechos; poucos
   MB/dia; cômputo noturno limitado pelos dados intraday já buscados pelos estudos.

## Pré-registro de leitura (anti-garimpo)

Métricas declaradas ANTES da primeira leitura: distribuição de rejeições por degrau; ±1R
renunciado por degrau (soma e mediana); split qualidade×capacidade; win rate ±1R
aceitos×rejeitados por faixa de score. **Primeira leitura formal: mesa após ≥5 sessões de
coleta.** O instrumento não é alavanca: nenhuma mudança de política nasce dele sem rito a seis
mãos com leitura pré-registrada.

## Janela de deploy (regra de congelamento)

Verde até **domingo 30/08 à noite** → entra antes da 4ª sessão (segunda 31/08) e a coleta
começa junto da semana de medição, sem deploy DURANTE ela. Não ficando pronto → espera o
pós-gate (6/09+). Sem meio-termo.

## Aceite

1. Sessão completa registrada com contagem batendo com o universo visto pelo funil;
2. Desfechos computados na régua do estudo de entrada (amostra conferida à mão pelo Fable);
3. Teste de equivalência do caminho quente verde;
4. Linhas-candidatas hasheadas emitidas com `ledger_admission_authorized=false`;
5. Suíte + 5 portões + auditoria cruzada (implementa Codex, audita Fable).

## Assinaturas

- **Dudu:** ASSINADO — 29/08/2026 ("Vamos começar pelo 1").
- **Fable:** ASSINADO — 29/08/2026 (autor).
- **Codex:** pendente (GO técnico + implementação).
