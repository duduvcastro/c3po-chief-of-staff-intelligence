# R2D2 — Sondas A/B e backtest do Candidato F

**Status:** runner de evidência para a mesa; nenhuma política é alterada.

**Época observada:** `policy-a-resume-2026-08-26`, desde
`2026-08-26T13:30:24.983322Z`.

**Retenção:** 30 dias, com `expires_at` no laudo e retenção equivalente no
artefato privado do GitHub Actions.

## Hipótese

A régua principal hoje recalcula, a cada observação:

`E = max(stop_original, high_water_close - 2,5 × ATR_vivo)`

Como o ATR pode subir mais rápido do que o `high_water`, `E` pode cair. O
contrafactual F muda uma única regra:

`F(t) = max(F(t-1), E(t))`

O watcher rápido, quando habilitado e com ATR fresco, já persiste uma catraca
própria e exige dois ticks. O laudo separa `fast_exit_rule` de saídas do ciclo
principal para não atribuir à régua principal uma execução feita por outro
motor.

## Sonda A — devolução associada ao afrouxamento

- População: episódios orgânicos, US, flat-to-flat e fechados, abertos na
  época 2; episódios corrigidos ou de `operator_wind_down` não entram.
- Relato individual: todo episódio vencedor aparece com token SHA-256
  irreversível, sem símbolo, fills ou barras cruas.
- Cobertura fail-closed: antes de calcular qualquer resultado, o runner exige
  um arquivo Massive para cada uma das 20 sessões XNYS de lookback e para cada
  sessão entre a primeira entrada e a última saída da coorte. Ausência de uma
  sessão aborta o laudo; ausência de trajetória observável ou de ATR suficiente
  censura o episódio e nunca vira efeito zero.
- Relógio: janelas fixas de cinco minutos de Nova York; cada barra agrega as
  1–5 linhas reais emitidas pelo Massive na janela. Minuto sem negócio elegível
  não gera linha no provedor e não é tratado como corrupção. Janela vazia não
  gera barra; não há `forward-fill`, interpolação nem preço sintético.
  `high_water` usa closes, como o harness original do Candidato E.
- ATR: média simples dos 14 true ranges que `compute_technical_snapshot`
  usava na janela móvel de 40 barras, com o mesmo piso de `0,4%` do preço.
- Cruzamento atribuível à catraca: primeiro close `<= F` e `> E`. Se também
  rompe E, a diferença não é atribuída a F.
- Fronteira temporal: só entram closes completos cujo `bar_end` seja anterior
  ou igual à saída real. Uma barra iniciada antes, mas fechada depois da
  saída, é excluída integralmente.
- Fill contrafactual: preço do close com a mesma fricção de saída do paper
  ledger. Episódios com escala ou parcial ficam visíveis, mas censurados.
- Saídas: P&L líquido real, P&L F, devolução evitável em USD, maior distância
  acumulada entre a catraca F e a régua E em bps e distribuição agregada.

## Sonda B — arrependimento de stop-out

- Stop-out: SELL final com `fast_exit_rule` `hard_stop` ou
  `chandelier_2tick`, ou motivo equivalente do ciclo principal.
- Janela de recuperação: barras de um minuto estritamente posteriores ao
  minuto da saída, até o fim da mesma sessão regular de Nova York. A barra da
  saída é excluída porque a ordem intraminuto é desconhecida.
- Entrada: fill médio ponderado pelas quantidades compradas.
- `1R`: entrada menos o `stop_price` original persistido no BUY.
- Saídas: percentual que voltou acima da entrada; percentual que chegou a
  `+1R`; ambas com denominador elegível explícito. Sem barras observáveis do
  símbolo na sessão da saída, o episódio é censurado; denominador zero é `N/D`,
  nunca `0%`.

## Backtest E × F

O harness ad hoc de 20/08 foi recuperado do registro local. O replay congela:

- commit da política E: `bc79ca195c19bee9b9ef18c3098d28ae6c149597`;
- 40 nomes: 20 NASDAQ e 20 NYSE registrados no harness;
- sessões 06–19/08/2026, barras de cinco minutos;
- capital de USD 1 milhão, 20 posições, 5 bps de fee, 5 bps de slippage e
  lookback de 40 barras;
- fundamentos neutros do próprio `backtest.py`;
- E: stop inicial 2×ATR, trail 2,5×ATR e budget de risco de 0,03% do NAV;
- F: tudo idêntico a E, acrescentando somente `max(F anterior, E atual)`.

Para cada variante, a taxa de saída precipitada é a fração dos legs de saída
por stop em que uma barra posterior da mesma sessão voltou acima do custo
médio da entrada. A barra da própria saída é excluída. A Sonda B permanece a
medida canônica da produção e acrescenta o limiar de `+1R`, indisponível no
schema congelado do backtest.

Os bytes da resposta EODHD usados em 20/08 não foram retidos. A nova execução
usa as mesmas datas e símbolos sobre o arquivo Massive de um minuto,
checksumado e agregado para cinco minutos. Essa troca fica no laudo e impede
qualquer alegação de reprodução byte a byte do número histórico.

A reconstrução usa a semântica publicada pelo Massive: em cada janela fixa de
cinco minutos, `open` é a primeira linha real, `high/low` são os extremos,
`close` é a última linha real e `volume` é a soma. O piso de 70 barras por
símbolo/sessão permanece fail-closed depois da agregação. O run `33714916267`
usou a implementação v1, que descartava a janela inteira quando uma das cinco
linhas de minuto não existia; o JSON parcial dessa execução não foi publicado e
é explicitamente superseded pela montagem corrigida, preservada neste schema v3.

Essa correção da montagem pode fazer os números absolutos de E divergirem do
relatório de 20/08. E e F, porém, recebem exatamente o mesmo conjunto de barras
formadas, de modo que a comparação pareada permanece internamente válida quando
o estudo completa. A materialidade dessa divergência não é decidida
automaticamente: se a mesa a considerar material, E deve ser re-atestado com a
montagem nova antes de qualquer conclusão de política.

Se qualquer símbolo/sessão continuar abaixo das 70 barras formadas, o runner
publica um laudo `PARTIAL/BLOCKED` self-hashed com a matriz integral de
shortfalls, `candidate_e`, `candidate_f` e o delta pareado nulos. Só depois do
artefato e do anexo serem publicados o workflow termina vermelho. O bloqueio
volta à mesa; não há attrition, redução do piso, preenchimento de preço ou
interpolação.

O run `33716979776` produziu um backtest E×F válido, mas o seu arquivo de
minutos terminava em 21/08 enquanto a coorte das Sondas A/B começava em 26/08.
O laudo v2 das sondas não verificava essa interseção e classificou ausência de
trajetória como observação elegível de efeito zero. Esses números A/B são
inválidos e explicitamente superseded pelo schema v3; o backtest E×F do mesmo
artefato permanece válido porque usa o universo e as sessões congelados de
06–19/08.

Referências primárias: [Custom Bars (OHLC)](https://www.massive.com/docs/rest/stocks/aggregates/custom-bars)
e [Why are there missing aggregates?](https://massive.com/knowledge-base/article/why-are-there-missing-aggregates-in-massives-data).

O Candidato G não roda nesta primeira comparação: manter E×F com uma única
variável reduz ambiguidade. O resultado pode justificar uma nova obra para G,
mas não a autoriza.

## Execução e segurança

O workflow é manual, exige a frase exata `RUN R2D2 CHANDELIER STUDY`, a revisão
auditada já implantada e janela de 00:00–08:00 BRT. A consulta abre transação
PostgreSQL `READ ONLY` e verifica `transaction_read_only=on`; nenhuma API
externa é chamada. Saem do host somente os dois laudos JSON, o SQL exato, o
digest textual do pacote congelado e o manifesto de checksums. Os contêineres de
estudo rodam com o UID/GID do usuário operacional, no diretório exclusivo do
`RUN_ID`. O pacote é validado antes da extração; seu SHA-256 entra no laudo e
no manifesto portátil. Todos os arquivos recebem SHA-256, e o resumo factual
é anexado à PR #348.

O runner não altera tabelas, imagens, workers, stops, sizing, flags ou estado
do experimento. Resultado favorável a F é apenas insumo da mesa e exige nova
política versionada, auditoria do Fable e autorização do Dudu.
