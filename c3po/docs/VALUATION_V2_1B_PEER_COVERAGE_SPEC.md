# Valuation V2.1b — Fechamento de Dados de Qualidade dos Peers

**Status:** congelada na PR #205 · **Escopo:** dados somente ·
**Dependência:** A/B v3 reprovado de 23/08/2026 · **Consumidores:** nenhum

## 1. Objetivo e limites

Dar ao ajuste V3.1 o conjunto de dados que a especificação pretendia testar,
sem modificar fórmula, banda P4, peso de consenso, TP oficial, shadow vivo ou
qualquer consumidor. O V3 permanece reprovado até novo A/B imutável.

Esta fronteira corrige dois problemas medidos:

1. `returnOnEquity` não existe em `/stable/ratios`; existe em
   `/stable/key-metrics`. O normalizador atual grava `roe=None` em 100% dos
   6.552 registros anuais examinados.
2. Os pacotes V2.1 cobrem somente 32,83% das referências de peers na B3 e
   51,26% nos EUA, pois foram coletados apenas para os 693 alvos rastreados.

Não há coleta recursiva: peers de peers não entram no escopo.

## 2. Emenda de fonte, sem mudança de fórmula

A base `fmp_forward` continua exigindo ROE anual e receitas FY1/FY2 positivas
do mesmo pacote FMP. A origem correta do ROE passa a ser:

```text
ROE_i = key_metrics_annual.returnOnEquity da observação mais recente
        com fiscal_year_end <= as_of

g_i = revenue_avg_FY2 / revenue_avg_FY1 - 1
```

O crescimento continua vindo de `analyst_estimates_annual`. Não existe
fallback para `ratios_annual.roe`, derivação por DuPont, mistura com Chewie ou
preenchimento. Campo ausente torna a base indisponível, como antes.

A PR de dados precisa acrescentar explicitamente `roe`, normalizado do campo
bruto `returnOnEquity`, a cada linha de `key_metrics_annual`. O cliente atual
descarta esse campo ao normalizar market cap, EV, ROIC e métricas por ação;
alterar apenas o leitor V3 sem corrigir o normalizador não resolve a cobertura.

Essa emenda substitui somente a frase `ROE anual mais recente em
ratios_annual` do §2.2 de `ENGINE_V3_SPEC.md`. Toda a fórmula §2.3 permanece
byte por byte congelada.

## 3. Universo determinístico de fechamento

Para cada mercado, a coleta parte do snapshot diário completo dos alvos:

```text
T = conjunto canônico de símbolos-alvo do valuation_v2_data
P = união canônica dos peers diretos registrados nos pacotes de T
C = P - T
```

- `.SA` é removido apenas para a chave canônica; o símbolo do provedor é
  preservado no pedido e no snapshot.
- `C` é ordenado lexicograficamente e cada símbolo é tentado exatamente uma
  vez por ciclo.
- O conjunto fica gravado no snapshot com contagens, hash e statuses por
  endpoint. Mudança no grafo em outro dia gera outro snapshot; nunca altera o
  anterior.
- Não se buscam peers de `C`, evitando expansão recursiva e custo aberto.

## 4. Pacote leve por peer

Cada símbolo de `C` recebe somente:

1. `key_metrics_annual`, para ROE anual normalizado;
2. `analyst_estimates_annual`, para receitas FY1/FY2.

Os múltiplos continuam vindo dos snapshots point-in-time de universo/Chewie,
como no A/B original. Um peer sem múltiplo no mesmo conjunto congelado não
entra na regressão, mesmo que tenha qualidade FMP completa.

O teto observado desta primeira fronteira é de 1.299 peers diretos ainda sem
pacote (204 B3 + 1.095 US), portanto até 2.598 chamadas adicionais por ciclo
com o grafo atual. O relatório grava chamadas tentadas, respostas válidas,
vazias e erros; o job continua na janela off-hours e não compartilha caminho
com o R2D2.

## 5. Persistência e cobertura

O snapshot aditivo `valuation_v2_peer_quality` contém:

- `as_of`, mercado, símbolos-alvo e hash do grafo direto;
- pacote normalizado por peer, com `fetched_at` e status independente dos dois
  endpoints;
- contagem por referências e símbolos únicos;
- cobertura estrutural: alvo com lista de peers, com pelo menos quatro peers
  tentados, com pelo menos quatro pares `fmp_forward` completos e com ajuste
  efetivamente elegível por métrica;
- nenhuma substituição do snapshot `valuation_v2_data` existente.

Não há threshold percentual inventado para declarar sucesso. A coleta termina
quando todos os peers diretos do grafo congelado foram tentados. A suficiência
estatística continua sendo a regra já congelada de pelo menos quatro peers
completos por perna.

## 6. Chewie e novo congelamento

O snapshot Chewie usado em 23/08 ainda era a primeira coorte US: 1.186/3.859
NASDAQ e 714/2.324 NYSE. No momento do probe, o snapshot corrente era o mesmo,
portanto H3 ainda não podia ser comparada.

O próximo A/B só pode congelar um novo conjunto depois de:

0. todos os pacotes dos alvos `T` serem re-coletados após a correção do
   normalizador, com a contagem de `roe` não nulo e os statuses do provedor
   verificados no relatório pré-A/B; cobertura igual a zero falha fechado;
1. o ciclo Chewie publicar uma fotografia nova e acumulada;
2. o job V2.1b tentar todo o grafo direto dessa fotografia;
3. o relatório pré-A/B mostrar separadamente elegibilidade `fmp_forward` e
   `chewie_trailing` por mercado e por métrica.

Cobertura Chewie maior ajuda a resolver múltiplos e a base trailing, mas nunca
preenche um campo ausente da base forward.

## 7. Testes vinculantes

1. Payload de `ratios` sem `returnOnEquity` não fabrica ROE.
2. `key-metrics.returnOnEquity` é normalizado e preserva zero válido.
3. O ROE escolhido é o último fiscal disponível em `as_of`, sem lookahead.
4. ROE e FY1/FY2 pertencem ao mesmo pacote FMP; fonte cruzada é recusada.
5. O fecho contém somente peers diretos, sem recursão e sem duplicata canônica.
6. Símbolo B3 mantém o símbolo de provedor e resolve `.SA` deterministicamente.
7. Falha de um endpoint não apaga a evidência nem o status do outro.
8. O snapshot é imutável e uma nova execução não sobrescreve evidência antiga.
9. O novo congelamento recusa pacotes-alvo anteriores à correção do
   normalizador ou uma cobertura de ROE igual a zero.
10. O engine v2 reproduz os mesmos resultados e nenhum consumidor importa o
   novo snapshot.
11. O novo A/B só começa após reproduzir o baseline v2 e validar hashes de
    todos os snapshots, igual ao harness aprovado na #203.

## 8. Próximo gate

Após auditoria desta spec: PR de dados V2.1b, backfill off-hours, novo conjunto
congelado, novo manifest e repetição do A/B. Somente esse relatório poderá
dizer se a fórmula V3.1 passa ou falha quando realmente recebe combustível.

Continuam bloqueados: shadow v3, qualquer consumidor, alteração de fórmula,
afrouxamento de P4 e reinterpretação do A/B reprovado de 23/08.
