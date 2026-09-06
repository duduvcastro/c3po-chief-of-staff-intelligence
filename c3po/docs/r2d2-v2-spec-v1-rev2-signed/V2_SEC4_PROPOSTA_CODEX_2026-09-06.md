# Proposta do Codex para o §4 da spec V2 V1

Objeto: uma política candidata para shadow prospectivo. Os números abaixo são escolhas de projeto para congelamento, não parâmetros otimizados nem eficácia demonstrada pelo piloto de oito sessões. Fable incorpora e audita; o contrato completo recebe versão e hash antes da primeira coleta. Esta proposta não é ordem de implementação, deploy, BUY ou reabertura da V1.

Referências locais: R1 rev2 com assinatura do Dudu, SHA `181127e85d5e505d503a391127b3c71417e93526527223638c6637a37d1a8c31`; passo2 público `e276be5093126c07f526a01dad08a5941f9ec1e08dda62dce0001d8d5b690e81`. Os fatos do código estão em `risk-semantics.md` (SHA `d5d94ff5bf600fd973e7f57e2380344c65dd25c864b8225260538b7ef0237691`).

## 4.1 Universo e população observada

- Ações ordinárias e ADRs de ações ordinárias listadas na NYSE/NASDAQ; long-only; ETFs/ETNs, preferenciais, warrants, OTC, derivativos e B3 fora desta candidata. Classificação ausente gera `DATA_INELIGIBLE`, com contagem, sem adivinhar o tipo.
- Preço de referência de entrada ≥ US$5. Liquidez: média de `close * volume` em USD nas **20 sessões regulares completas anteriores**, ≥ US$15 milhões/dia. São necessários 20 dias válidos; sem extrapolar volume parcial do dia. O valor 15 milhões é herdado; a definição ADV20 e o piso de preço são propostas novas e precisam constar da versão congelada.
- Spread `(ask-bid)/mid <= 0.0020` (20 bps), bid/ask positivos e não cruzados, cotação de idade ≤10 s no instante da decisão. Esses limites são propostos, não alegados como defaults atuais.
- Uma observação por nome/sessão às 10:00 `America/New_York`, durante sessão regular. Guardar o primeiro snapshot válido entre 10:00:00 e 10:01:00; se não existir, contar ausência, sem tentar outra hora. Universo e elegibilidade usam apenas informações disponíveis até esse snapshot. Guardar origem, versão e timestamps dos inputs; nenhuma recomposição retrospectiva com a lista de ações de hoje.
- Gerar população **antes de R1 e antes da capacidade da carteira virtual**. Registrar candidatos aceitos por R1 e controles com risco válido acima do corte, com a mesma regra de barreiras e observação. Falta de caixa, posição já aberta e limites de exposição são decisões da carteira, não exclusões silenciosas dessa população de pesquisa.
- Uma carteira virtual por política, NAV inicial US$1.000.000; no máximo uma posição aberta por nome, sem piramidar. Empates de admissão por capacidade: ordem lexicográfica do SHA256 de `versao|data_sessao|simbolo`, sem rank de composite/fundamental/technical. Persistir essa ordem.

O relógio usa o calendário oficial da bolsa, inclusive feriados e sessões curtas. A sessão regular habitual é 09:30–16:00 ET; não converter para um horário BRT fixo durante todo o ano. [NYSE — calendário e horários](https://www.nyse.com/markets/hours-calendars).

## 4.2 Filtro R1 e dados inválidos

Um único filtro de score: campo top-level `risk_score` persistido no snapshot da decisão, numérico nativo, finito, em [0,100], **sem coerção de bool/string**, sem arredondamento e sem substituição por outro score.

- Elegível por R1: `risk_score <= 44.10596901963097`.
- Controle excluído por R1: risco válido `> 44.10596901963097`.
- Ausente, tipo inválido, não finito ou fora da escala: `DATA_INELIGIBLE`, separado do braço de alto risco, contado por motivo.

O corte não muda se a distribuição prospectiva mudar. Registrar a origem do score; o fallback US tem mínimo matemático 49,9 e, portanto, não passa R1. Isso é consequência da fórmula, não evidência de composição da amostra nem motivo para esconder seus candidatos. Não reutilizar os gates de score da V1 como filtros implícitos adicionais.

## 4.3 ATR diário, stop e sizing

ATR(14) Wilder em OHLC diário das sessões regulares, somente até D−1. Proponho janela inicial fixa: **61 barras diárias completas consecutivas**, que fornecem 60 true ranges. `TR_i=max(H_i-L_i, abs(H_i-C_prev), abs(L_i-C_prev))`; seed = média dos primeiros 14 TR; atualizar cada TR restante por `(13*ATR_prev+TR_i)/14`. Sem dados suficientes/íntegros ou ATR não positivo, contar inelegibilidade; nenhum fallback para ATR intradiário.

A janela fixa é uma definição nova para eliminar diferenças de seed/histórico entre fornecedores; não afirmar que reproduz exatamente a implementação histórica de D'. Registrar barras, calendário, fatores corporativos conhecidos e hash da fonte usados no cálculo.

Múltiplo **1,5**; stop inicial fixo, sem alargar, trailing, mudança por regime ou defesa intradiária discricionária. A conta considera as duas pernas da fricção:

```
s = 0.0010; f = 0.0004
P = (bid+ask)/2 no snapshot válido de entrada
B = P * (1+s)                   # fill de compra modelado
C = B * (1+f)                   # desembolso unitário
S = B - 1.5*ATR                 # preço-gatilho do stop
net_sell(x) = x*(1-s)*(1-f)
R_unit = C - net_sell(S)
T = (C + R_unit)/((1-s)*(1-f))   # preço-gatilho do alvo líquido +1R
```

Exigir `0 < S < P < T`, valores finitos e `R_unit > 0`; caso contrário, geometria inelegível e contada igualmente nos dois braços. Em particular, ATR muito pequeno pode produzir S acima de P por causa do slippage de compra; não admitir stop já ultrapassado. Persistir P/B/C/S/T/R_unit na entrada; nenhuma geometria futura recalcula o stop daquele episódio. O risco nominal por posição é **0,02% do NAV**, herdado do parâmetro de risco atual: `q_risk = 0.0002*NAV/R_unit`. Esse é risco modelado até o stop, não limite garantido diante de gaps.

**Endpoint novo proposto:** estas fórmulas entregam P&L líquido de −R/+R em torno de zero econômico. Não são o `net0±R` histórico de M1: naquele motor, `net0` é o retorno líquido ao preço de sinal (em geral negativo pela fricção), e as barreiras são deslocadas em torno desse valor. A spec deve renomear/fixar esse endpoint novo para R1/H1 e registrar a mudança antes da coleta. O corte de risco candidato não herda uma certificação do novo endpoint a partir do piloto antigo.

Quantidade = menor limite de risco, caixa e capacidade; arredondar para baixo a seis casas. Para os limites abaixo, usar custo unitário C na admissão:

- máximo 6% do NAV por nome; 48% por mercado (NYSE/NASDAQ compõem juntos o mercado US);
- exposição bruta máxima 95%, caixa mínimo 5%; sem margem/alavancagem;
- **teto adicional de exposição prevista para overnight: 48% do NAV total**. Como todas as entradas desta política podem ser carregadas, esse teto já limita a admissão. No universo US long-only desta versão, coincide com o teto de mercado;
- bloqueio de novas entradas virtuais quando a perda do NAV no dia, desde o fechamento anterior, atingir 2%; as saídas continuam;
- **retirar o piso de 2% do NAV por posição da função legada de sizing**. Com ATR diário, esse piso pode ultrapassar o risco monetário de 0,02%. Quantidade sem capacidade positiva → candidato registrado, sem posição virtual.

Limites percentuais são controles de admissão. Se a marcação posterior ultrapassá-los, registrar excesso e bloquear aumento; não inventar liquidação compulsória que acrescentaria uma regra de saída. A perda diária também usa marcação causal, com ausência de marca contada e nova admissão bloqueada até observabilidade válida.

## 4.4 Horizonte e saídas determinísticas

**N = 10 sessões da bolsa, incluindo a sessão de entrada.** Saídas: primeiro stop S ou alvo T, encerramento por evento, ou saída temporal cinco minutos antes do fechamento oficial da décima sessão. Não reentrar no mesmo nome no mesmo dia após uma saída. Sem operação em pré/pós-mercado.

O alvo líquido +1R é uma escolha nova desta candidata; o uso de 1,5 ATR e N=10 não transforma a política inteira numa réplica literal de D'. A marcação intradiária serve às regras fixas, não escolhe outra saída.

Na abertura abaixo do stop, usar o primeiro preço regular negociável observado e aplicar fricção; a perda pode exceder 1R. Para alvo, usar T conservadoramente se houver evidência de execução a T ou melhor. Uma barra que toca ambas as barreiras sem evidência temporal suficiente permanece **ambígua** no estudo; na carteira virtual, usar a saída pelo stop como convenção conservadora e identificar a convenção no ledger. Não apresentar essa convenção como ordem de eventos observada. Preço de stop não garante preço de execução. [Investor.gov — tipos de ordem](https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work/types-orders).

Todos os episódios permanecem no inventário: barreira superior, inferior, ambíguo, encerrado por tempo/evento e não observável têm contagens próprias. Encerramento temporal/evento entra com P&L realizado na expectância; não vira automaticamente acerto ou erro de barreira. Falha de dados mantém pendência/indeterminação com gate próprio; não usar última cotação antiga como saída fictícia.

Antes da implementação, o contrato de eventos/barra precisa fixar desempate, primeira barra após entrada e execução de saída temporal em dado ausente. A proposta não autoriza substituir esses casos por preços fabricados para fechar a conta.

## 4.5 Overnight, earnings e eventos corporativos

- Não admitir posição se a informação disponível no snapshot indicar earnings entre a entrada e o encerramento planejado, inclusive. Calendário de earnings sem cobertura verificável → inelegível por dados, contado. Não aplicar retrospectivamente uma data que só foi conhecida depois.
- Se um anúncio novo passar a conflitar com a janela de uma posição aberta, marcar saída por evento na **primeira cotação regular válida após a detecção**, com custos e timestamp; sem esperar novo sinal técnico. Um anúncio fora de horário produz intenção para a próxima sessão regular.
- Orçamento proposto de perda de gap: **1% do NAV no início do dia**, agregado nas posições carregadas. Medir a soma das perdas econômicas negativas de fechamento anterior a primeira marca válida de abertura, sem compensá-las com ganhos de outras posições. Reconciliar quantidade/preço após splits e dividendos/recebíveis devidos; não usar variação nominal bruta que fabricaria uma perda por ação corporativa. Exceder o orçamento gera falha de risco da candidata (`V2_CERTIFICATION_FAILED_GAP`); não apagar os episódios. É um critério de avaliação, não promessa de contenção da perda.
- Usar preços de execução não ajustados; splits ajustam quantidade e níveis de preço sem criar lucro; dividendos devidos a posições carregadas entram como recebível causal e depois caixa. Toda ação corporativa precisa de identidade/data/fator conhecidos no instante pertinente. Evento não suportado bloqueia a avaliação/contabilidade afetada, com motivo explícito; não excluir retroativamente o perdedor.

## 4.6 Custos

Manter US paper: **10 bps de slippage e 4 bps de taxa em cada lado**, aplicados sequencialmente como nas fórmulas. A soma aproximada round-trip é 28 bps; a conta efetiva preserva os produtos. O spread é gate de admissão, sem somar uma segunda cobrança de spread ao modelo já declarado. Dividendos, splits e cash/NAV têm reconciliação própria; não confundir custos de infraestrutura com fricção por trade.

## Ajustes necessários nos §§3/6 antes do GO da spec inteira

1. **Separar a assinatura da candidata R1 da certificação.** O sinal histórico Q4−Q1 é secundário/exploratório. R1 testa prospectivamente elegíveis versus controles válidos; H1 testa edge absoluto. Falta de aprovação é falha de certificação, não prova de inexistência de efeito.
2. **Fixar população/estimando/censura para a nova geometria.** ATR diário e N=10 alteram o endpoint. Reutilizar infraestrutura de M1 não significa que o antigo estimador intradiário certifica uma carteira multi-dia sem alteração. Declarar o tratamento de tempo, evento, ambiguidade e ausência nos denominadores; publicar também cobertura/censura por braço. A carteira admite menos episódios que o inventário de pesquisa, e as duas populações não podem ser confundidas.
3. **Orçamento de erro explícito.** Se R1 e H1 tiverem duas leituras cada (15 e 20 sessões de entrada, sempre após maturação), alpha unilateral 0,0125 por leitura soma 0,05 por Bonferroni, supondo testes marginais válidos. Isso não deixa um segundo orçamento livre para declarar H2/H3/H4 certificados. Fixar família, hierarquia e regras antes da coleta. Gates de risco/viabilidade podem reprovar, mas não substituem evidência positiva de edge.
4. **Dependência multi-dia.** Episódios de sessões vizinhas compartilham até dez sessões de preços. Sorteios iid do dia de entrada não preservam automaticamente essa dependência. O desenho definitivo deve fixar reamostragem temporal compatível com o horizonte e justificar/calibrar cobertura antes de usar um LCB nominal como certificação. 15/20 sessões são limites de leitura propostos, não prova de informação suficiente. Se a validação não sustentar inferência, leitura `NOT_ESTIMABLE`, sem promoção; ajustar horizonte de coleta/método pelo rito antes de coletar, não após ver resultados.
5. **H3 precisa de aprovação positiva.** `UCB < 0` evidencia resultado negativo, mas seu complemento não demonstra expectância não negativa. Uma política não recebe GO porque um intervalo amplo ainda contém zero. Fixar a regra positiva de aprovação e seu alpha, ou manter H3 apenas descritiva/como veto sem alegar certificação econômica.

Entrega concluída como proposta concreta do §4 e lista delimitada de requisitos estatísticos do contrato completo. Nenhuma busca adicional nos oito dias, reconstrução, bootstrap, leitura de preços, SSH/DB ou alteração operacional foi realizada para escolher estes parâmetros.
