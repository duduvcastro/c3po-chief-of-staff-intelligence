# Valuation — TP oficial único (Passo 0 do §7-bis, Valuation Engine V3.2 rev 7)

Referência normativa: `evidence-relay/ENGINE_V3_2_SPEC_REV7_2026-09-07.md` (sha256 `d31ed90e…`, congelada a três em 07/09/2026), §7-bis (P2 "um só para tudo"), invariantes I-TP1..I-TP4, decisão do dono §10.8 (estudos e gradação migram no mesmo passo).

## O que este passo faz

1. **Registros de previsão imutáveis** (`valuation_predictions`, DDL `db/048_valuation_official_tp.sql`): cada ciclo que um produtor publica (`valuation_universe` por mercado; `security_valuation` sob demanda B3) vira uma linha por símbolo — `tp`, `buy_in`, `internal_tp`, consenso de referência, preço, decomposição e `row_sha256` (hash do conteúdo). Chave: `(source, source_version, market, symbol, cycle_id)`. Nunca atualizados nem apagados (gatilhos `BEFORE UPDATE OR DELETE` recusam).
2. **Seleção oficial por geração** (`valuation_official_selection`): uma linha por geração = o conjunto de ciclos **completos e válidos**, um por mercado (B3, NASDAQ, NYSE), cujas previsões **são** o TP oficial. Uma geração só é ativada quando os três mercados têm ciclo válido; a troca (Passos 1 e 2) e o rollback são a **inserção** de uma nova geração apontando para ciclos existentes; a anterior fica legível. Um único INSERT: quem lê vê a geração anterior ou a nova, nunca mistura.
3. **Produtor do Passo 0**: o motor oficial atual — as linhas canônicas dos screeners (`our_tp`), exatamente o que o site já exibe. `tp_source = official_blend_v1`. Nenhum número do produtor muda.
4. **Consumidores operacionais leem a seleção e não calculam**:
   - **One Pager** (`one_pager.py`): `c3po_tp`/`buy_in` vêm só da linha oficial (`_official_valuation` → `valuation_official.official_row`), estampados com `tp_source`, `official_generation_id`, `official_cycle_id`. O blend local com consenso e o cálculo local de buy-in foram removidos; os métodos internos continuam **só como painel diagnóstico** (`internal_framework_*`). Sem linha oficial (ativo fora do universo canônico; B3 quando o produtor não consegue construir) o One Pager **não é gerado**, com o motivo — nunca um TP próprio.
   - **R2D2 v1** (`r2d2.py`, pausado): as linhas canônicas vêm de `official_rows(market)` (seleção vigente), não de um snapshot cru; o "backfill de valuation do dia" (que chamava o motor do One Pager) foi removido — sem linha oficial o ativo cai para o degrau técnico provisório, como antes para os provisórios.
   - **Site / candidatos** (`B3CandidateResponse`): resposta estampada com `tp_source`, `official_generation_id`, `official_cycle_id` (I-TP3).
   - **Estudos e gradação** (`valuation_accuracy`, adaptador dos estudos, replays): continuam lendo os registros históricos por fonte/versão/instante e `valuation_change_records.new_tp/changed_at`; nunca a seleção vigente para reavaliar chamadas antigas.
5. **Varredura de CI** (`tests/test_valuation_official_contract.py`): nenhum módulo fora dos produtores/motores pode **atribuir** `our_tp`/`c3po_tp`/`calibrated_tp`/`tp` a partir de uma computação; testes de contrato provam que One Pager, R2D2 e a resposta servida resolvem a **mesma** linha para a mesma `(mercado, símbolo, geração)`.

## Baseline (TP-A) e diferenças reconhecidas

Baseline = `our_tp` canônico dos snapshots `valuation_universe`. Medição read-only em produção (07/09/2026, 39 One Pagers de 15/08 a 29/08): onde havia linha canônica no instante, o One Pager já exibia **o mesmo TP** em 26/27 casos (1 caso intradiário JPM 20/08 com ordem de ciclos, +9,9 %); em **12/39** casos não havia linha canônica (MSFT/AMZN nos primeiros dias, antes de o universo os cobrir; MHVYF ×4, listagem estrangeira nunca no universo) e o One Pager calculava localmente. Depois deste passo esses casos **recusam** com motivo até o produtor oficial cobri-los. Site e R2D2 v1 já liam a linha canônica: igualdade por construção (mesmo ciclo). Recibo completo em `outputs/fable-tp0-baseline/`.

## Operação

- Primeira geração: ativada automaticamente na primeira publicação de ciclo após o deploy (os três mercados já têm ciclos válidos). Enquanto não houver geração, One Pager recusa e R2D2 não tem linha canônica — sem cálculo local.
- Rollback: `valuation_official.select_generation(database, cycles=<ciclos da geração anterior>, ...)` insere uma nova geração; nada é apagado.
- O que este passo **não** faz: não tira o consenso do TP (Passo 1), não promove V3.2 (Passo 2), não apaga o código do motor interno do One Pager (Passo 3, com prova de ausência de uso), não muda constantes nem o V3 congelado.
