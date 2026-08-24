# Estudo de Política de Saída — Spec V1.1 (para congelamento)

**Status: CONGELADA a seis mãos em 24/08/2026** · incorpora integralmente as duas rodadas de condições do Codex · **Escopo:** pesquisa read-only · **Toca produção:** nada · **APIs:** zero · **Origem:** pergunta do dono (24/08/2026): "vemos +0,3% evaporar até o stop — a assimetria está errada?"

**Mudança estrutural vs. V1:** o relatório é dividido em dois painéis com peso de evidência distinto. O Painel I (observado + overlays) é vinculante; o Painel II (motor de barras) é exploratório e jamais autoriza mudança de estratégia por proxy histórico. O gate de calibração causal da V1 (§4 antigo) foi substituído: reconhecemos que barras de minuto não reproduzem decisões tomadas com cotações vivas e estado técnico intraminuto, e o desenho não finge o contrário.

---

## 1. Pergunta congelada

Sobre as MESMAS entradas que o R2D2 realmente executou:

- **(I — vinculante)** Alguma política de realização/proteção de ganho (take-profit, breakeven, trailing) domina a política atual, medida sobre as saídas REAIS do ledger com overlays que só podem antecipá-las?
- **(II — exploratório)** Quanto a largura do stop muda o resultado, medida num motor de barras internamente consistente, sem pretensão de reproduzir causalmente a produção?

O estudo responde com número; **não autoriza mudança nenhuma por si**. Qualquer alteração de política continua sendo mudança de estratégia versionada, a seis mãos, depois — pelos ritos do §9.

## 2. Dados e custos (só o que já temos)

- **Trades**: ledger paper do R2D2 — fills, quantidades, taxas e reason strings; trades `correction` excluídos (mesmo filtro da contabilidade #209).
- **Caminhos de preço**: minute aggregates do arquivo Day D (mercado inteiro, por sessão, verificados por sha256). Última barra: **2026-08-21**. Zero download novo.
- **Modelo de custos**: o do código, nunca reinventado. Leitura preliminar do Codex (a confirmar com citação no Entregável 0): entrada = 10 bps de slippage + 4 bps de fee, ambos já dentro do `average_cost`; `mark = quote / average_cost − 1` (custo de entrada embutido no mark); `net` = mark menos a perna de saída (10 + 4 bps); **sem dupla contagem**. Nascimento ≈ −14 bps de mark, ≈ −28 bps líquidos.
- **LOW (24/08)** está FORA da coorte de simulação (posterior à última barra): vive apenas no Entregável 0.

## 3. Unidade de análise e coorte

- **Episódio de posição**: do primeiro fill que sai de flat até a quantidade voltar a zero, incluindo aumentos e reduções parciais no meio. Toda métrica por trade é por episódio.
- **Coorte comum por painel**: os mesmos episódios avaliados por todas as políticas do painel. Episódio infactível para qualquer política do painel (dados faltantes, janela além de 2026-08-21) sai do painel INTEIRO e entra no contador de censura. Episódios ainda abertos no corte: excluídos e contados.
- As entradas (fills e custos de compra reais) são idênticas e fixas em todas as políticas; só as saídas variam.

## 4. Entregável 0 — co-assinado e ampliado (pré-requisito de tudo)

1. **Política vigente por extenso**: todas as camadas de saída (fast risk watcher, `hard_stop` e o cálculo do seu nível, regras de fim de dia, horizonte máximo, qualquer outra), com a **precedência COMPLETA entre regras**, citando código e parâmetros versionados.
2. **Decomposição dos −0,1400%**: confirmar com citação os 10 bps + 4 bps no `average_cost`; **teste de dupla contagem documentado** (leitura preliminar do Codex: não há — vira documento com prova).
3. **Semântica de mark e net** por extenso, e o **buffer de sobrevivência**: LOW nasceu ≈ −14 bps e saiu por `hard_stop` a mark −22 bps — ~8 bps de espaço econômico, dentro do ruído de minutos de qualquer ação líquida. A regra escrita tem que explicar por que o nível 218.2634 estava ali. Reason string completo anexado.
4. **EHC 24/08 11:48**: fill US$ 122,19 vs "awaiting live quote" US$ 121,73 (≈ +38 bps). 10 bps são o slippage configurado; **os ≈ 28 bps restantes exigem reconciliação de timestamps e cotações e NÃO podem ser chamados de slippage sem essa prova**. A reconciliação é entregável, com veredicto: staleness de exibição, defasagem de fonte de cotação, ou defeito real de modelagem de fill.
5. **O realizado de −US$ 39.981,68 em 21/08**: decomposição ao centavo, por episódio, com nome.

Se a regra escrita não explicar os casos nomeados, o Entregável 0 não está completo.

## 5. Painel I — VINCULANTE: observado + overlays (A, B, B', C, C')

- **A = a sequência real do ledger.** Não é simulada. Datas, preços, quantidades, taxas e P&L são os observados.
- **Gate de consistência (vinculante)**: reconciliação **ao centavo** de quantidades, fills, taxas e P&L por episódio contra o ledger; **alinhamento OHLC** — todo fill dentro de [low, high] da barra do seu minuto, com tolerância declarada para timestamps na fronteira de minuto. O gate **não promete reproduzir timestamps causais intraminuto** — reproduz contabilidade e compatibilidade com barras. Gate falhou → parar e investigar dados; jamais interpretar resultados.
- **Overlays só antecipam.** Cada política adiciona um gatilho sobre o caminho real de barras do episódio:

| ID | Overlay | Parâmetros (congelados) |
|---|---|---|
| B | Take-profit | fecha tudo quando net realizável ≥ +0,15% |
| B' | Take-profit | idem, ≥ +0,30% |
| C | Breakeven | após net realizável ≥ +0,30%, stop sobe para o nível de net = 0 (entrada + custos totais) |
| C' | Trailing | após net realizável ≥ +0,30%, stop segue o pico de preço a −0,40% |

- Disparo avaliado por OHLC da barra. **Se o overlay não disparar até a saída real, prevalece a saída real de A** — mesmo minuto, preço e custos do ledger. Nenhum estado técnico intraminuto é inventado.
- **Parciais**: reduções reais anteriores ao disparo permanecem como ocorreram; o overlay, ao disparar, fecha a quantidade remanescente do episódio naquele ponto.

## 6. Painel II — EXPLORATÓRIO: motor de barras (A_minute, D, D')

- Os três rodam no **mesmo motor reconstruível por barras**, com as mesmas convenções conservadoras do §7. Comparações válidas apenas DENTRO do painel.
- **A_minute**: reconstrução da política vigente com o que barras permitem. A distância entre A_minute e A real é reportada por episódio como **diagnóstico de fidelidade** — não vinculante, não entra em tabela como baseline observada.
- **D**: stop fixo de preço a −0,80% da entrada. **D'**: stop a −1,5 × ATR(14) diário da entrada — ATR pela fórmula de Wilder, congelada, calculada **somente com dados até D−1** da entrada (point-in-time, sem lookahead).
- No motor, pós-substituição do stop, o episódio é governado exclusivamente pelas regras **mecânicas simuláveis**: stop, fim-de-dia net-positivo (como implementada em produção), e horizonte terminal (o vigente do Entregável 0; na ausência, 10 sessões, declarado; saída terminal no close da última barra menos fricção).
- **Limitação declarada em texto no relatório**: este painel não reproduz decisões técnicas da produção; mede geometria de stop vs. ruído, não causalidade.
- **Consequência decisória**: D/D' **nunca** autorizam mudança de estratégia por proxy histórico. O máximo que o Painel II pode gerar é proposta de **shadow prospectivo** (cálculo diário paralelo em produção, read-only, logado), a seis mãos.

## 7. Gatilhos líquidos e precedência intrabar (ambos os painéis)

- **Todo gatilho de lucro é definido em P&L líquido realizável** (mark menos a perna de saída) — regra de 21/08: breakeven coberto por fricção nunca é descrito nem tratado como lucro.
- **Stops em nível de preço**, como no sistema vigente; conversões mark↔preço↔net declaradas no Entregável 0.
- **Ordem na mesma barra** (sempre contra a política testada): (1) gap de abertura além de um nível → executa no preço de abertura; (2) stop; (3) take-profit; (4) regra de fim de dia. Stop e alvo tocados na mesma barra → stop primeiro.
- **Ativação de breakeven/trailing computada na barra N só vale a partir da barra N+1** (nada de ativar e disparar na mesma barra).
- Relógio da simulação só enxerga barras ≤ minuto corrente; entrada = preço real do ledger, nunca derivado de barra.

## 8. Saídas do relatório (imutável, hasheado)

1. **Painel I (tabela A/B/B'/C/C')**: P&L total líquido, win rate, ganho médio × perda média, profit factor, max drawdown da curva realizada, tempo médio de posição, giro; **métrica diária = P&L realizado do dia / NAV contábil do fechamento anterior** (contabilidade #209), acompanhada da **curva econômica marcada**; % de dias com realizado ≥ +0,15%.
2. **Painel II (tabela A_minute/D/D')**: mesmas colunas + diagnóstico de fidelidade A_minute vs. A real.
3. **MFE/MAE dos episódios reais**: distribuição da excursão máxima favorável/adversa antes da saída real; em particular, quantos episódios tocaram net ≥ +0,3% e terminaram no vermelho (o número que decide a intuição do dono). **Churn**: tempo-até-stop; fração de stops a <15/30/60 min da entrada (o padrão LOW).
4. **Inferência**: diferenças **pareadas por episódio** (política X − baseline do seu painel), IC 95% por **bootstrap de sessão** (reamostram-se sessões, não episódios), n de sessões declarado.
5. Censura e exclusões contadas; tolerâncias e resultado do gate; sha256 dos inputs (corte do ledger + lista dos arquivos de barras).

## 9. Classificação piloto e regra de decisão pré-registrada

- **Com < 15 sessões na coorte, o relatório é PILOTO.** Nenhuma dominância autoriza proposta de mudança de estratégia. Autoriza apenas: (a) continuidade do paper como está; (b) **shadow** da(s) política(s) vencedora(s) do Painel I até acumular ≥ 15 sessões; (c) para o Painel II, no máximo o shadow prospectivo de D/D'.
- **Com ≥ 15 sessões de evidência observada** (paper + shadow): dominância = diferença pareada com IC de bootstrap de sessão excluindo zero E drawdown não pior. Painel I dominante → Codex redige proposta de mudança versionada, decisão a seis mãos. **A domina → pergunta encerrada com número**, registrada no blueprint do R2D2 (o desconforto do print é o preço estatístico de uma assimetria correta). Ambíguo → registra-se, sem mudança; a próxima janela decide. D×C' (stop largo + trailing) fica pré-registrada como candidata natural da fronteira seguinte SE D/D' e C' dominarem nos seus painéis.
- Parâmetros desta spec são convenção v1 declarada, não otimizada; **proibido ajustá-los por trade ou após ver resultados**; sensibilidade só em fronteira nova de estudo.

## 10. Execução e guardrails

- Roda no host de produção (barras e ledger vivem lá), **read-only**, off-hours, sem competir com captura.
- **Depois da #210 (desacoplamento do worker); sem competir com o A/B-2 de 25/08.**
- Zero API, zero escrita fora do relatório imutável, zero toque em worker/estratégia/consumidor.
- Runner: Codex. Auditoria do código contra esta spec: Fable. Leitura do resultado: a seis mãos.

---

**Assinaturas.**
**Fable** — co-assinada nesta versão, 24/08/2026. As oito condições da primeira rodada do Codex e a emenda dos dois painéis da segunda estão incorporadas integralmente; reconheço que o gate causal da V1 era impossível de passar com honestidade e agradeço a correção.
**Codex** — de-acordo declarado em 24/08/2026, condicionado a exatamente esta emenda (dois painéis; gate de contabilidade + OHLC sem promessa causal; episódios completos; coorte comum; gatilhos líquidos; ATR point-in-time D−1; precedência intrabar completa; piloto < 15 sessões não vinculante; D/D' → só shadow prospectivo). Condições incorporadas acima, verbatim em substância.
**Dudu** — de acordo dado em 24/08/2026. **SPEC CONGELADA A SEIS MÃOS.** Nenhum parâmetro se move até o relatório existir; o texto congelado é identificado pelo sha256 publicado junto ao repasse, e a cópia canônica deve ser commitada no repositório pelo Codex junto com a #210 ou antes do runner.
