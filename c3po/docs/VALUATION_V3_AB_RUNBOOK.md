# Valuation V3 - A/B-2 congelado de 24/08/2026

**Escopo:** pesquisa read-only · **Consumidores:** nenhum · **TP oficial:**
inalterado · **Fonte normativa:** [`ENGINE_V3_SPEC.md`](./ENGINE_V3_SPEC.md), §5.

Este runbook materializa o manifest imutavel e executa o A/B V2/V3 sobre 14
snapshots congelados: os 12 papeis originais mais os dois fechamentos
`valuation_v2_peer_quality` exigidos por
[`VALUATION_V2_1B_PEER_COVERAGE_SPEC.md`](./VALUATION_V2_1B_PEER_COVERAGE_SPEC.md).
O harness nao consulta provedores, nao busca o snapshot "mais recente", nao
persiste em Postgres e nao altera worker, screener, One Pager ou R2D2.

## Ordem obrigatoria

1. O codigo do motor V3 auditado deve estar mergeado e implantado.
2. Confirmar `pre_ab_ready=true` e os cinco gates verdes nos snapshots
   `B3_V2_PEER_QUALITY` e `US_V2_PEER_QUALITY` congelados neste harness.
3. Depois do fechamento seguinte e somente com GO a seis maos, gerar uma unica
   vez os dois pacotes macro com `as_of=2026-08-24`: Selic SGS 432 e curva US
   3Y/10Y. A curva de 24/08 fica elegivel pela disponibilidade conservadora
   D+1; tentativa anterior falha fechado.
4. Obter por consulta read-only os UUIDs exatos desses dois snapshots.
5. Construir o manifest passando os UUIDs explicitamente. Nao existe fallback
   para `latest`:

   ```bash
   python -m app.valuation_v3_ab build-manifest \
     --selic-snapshot-id UUID_SELIC \
     --us-curve-snapshot-id UUID_CURVA \
     --engine-commit SHA_COMPLETO_DO_COMMIT_COM_OS_MOTORES \
     --output /app/day-d-data/valuation-v3/ab-2026-08-24/manifest.json
   ```

6. Conferir e registrar o `manifest_sha256`. O manifest fixa, para cada
   snapshot, UUID, tipo, entidade, horario de publicacao e SHA-256 do payload
   canonico completo; tambem fixa os hashes dos dois arquivos de motor e dos
   dois pacotes macro. O proprio arquivo do harness tambem fica preso pelo
   SHA-256 para que a logica executada seja verificavel junto do resultado.
7. Executar o A/B somente contra esse manifest, apos nova decisao a seis maos:

   ```bash
   python -m app.valuation_v3_ab run \
     --manifest /app/day-d-data/valuation-v3/ab-2026-08-24/manifest.json \
     --harness-commit SHA_COMPLETO_DO_HARNESS \
     --output /app/day-d-data/valuation-v3/ab-2026-08-24/report.json
   ```

O gravador e imutavel: repetir bytes identicos e idempotente; tentar publicar
conteudo diferente no mesmo caminho falha.

## Gate anterior ao V3

O harness reconstroi primeiro o output V2 integral dos tres mercados. O hash
canonico precisa ser identico ao shadow aceito de 24/08 e as contagens
precisam permanecer `100/219/298`. O input B3 de risk-free nao e persistido
com toda a precisao no shadow antigo; por isso o harness procura, exclusivamente
dentro do intervalo que arredonda para o valor registrado, uma taxa que
reproduza o output inteiro byte a byte. A taxa encontrada fica no relatorio.

Se qualquer mercado falhar, nenhum `ValuationV3Engine` e construido e nenhum
numero V3 e emitido.

## Saida obrigatoria

O relatorio contem:

- V2, V3.1, V3.1+V3.2 e V3 completo, com deltas entre pernas;
- p50/p90 interno, vies mediano assinado e p50/p90 final por mercado e perfil;
- `low_conviction`, modelos disponiveis, atribuicao e as 15 maiores divergencias;
- cobertura/status do ajuste de qualidade, base usada e betas negativos zerados;
- status da janela Selic;
- watchlist congelada completa, preservando papeis repetidos por funcao de auditoria;
- hashes do manifest, do baseline reproduzido e do proprio relatorio.

O indice de qualidade combina os pacotes-alvo V2.1 com os pacotes de closure
congelados B3/US; pacotes-alvo vencem defensivamente uma colisao de chave. O
status `profile_not_eligible` e esperado para perfis fora do escopo V3.1. Se
o classificador nao emitir literalmente `quality`, essa categoria tambem
aparece na contagem de perfis em vez de ser preenchida ou renomeada.

## Bloqueios preservados

Mesmo com o A/B verde, continuam bloqueados: `valuation_v3_shadow`, troca do TP
do PDF, screeners, `pretrade_rank`, R2D2 e qualquer uso decisorio. O relatorio
volta para auditoria das seis maos antes da proxima etapa.
