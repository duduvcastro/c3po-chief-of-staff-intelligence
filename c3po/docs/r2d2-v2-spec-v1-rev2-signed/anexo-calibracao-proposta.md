# Proposta de anexo — calibração sintética anterior à coleta

**Estado: desenho para assinatura, sem implementação ou execução.** Vinculado à spec recebida SHA `0fd5ef615f007072c6e072a5996202712e8d1ab767596cdb7de818e7ea90029b` e à revisão `statistics-review.md`. A mesa primeiro corrige e assina o protocolo; só então autoriza implementar/executar a calibração. Coleta prospectiva exige o recibo aprovado dessa calibração e os demais gates. Reprovação leva a emenda pré-coleta, não a executar estudos reais para escolher um método vencedor.

## 1. Alvos e procedimento a avaliar

- Verdades: θ_R1=p_E−p_C, θ_H1=p_E, θ_H3=E[P&L_USD por episódio]. Nulos: θ_R1≤0, θ_H1≤0,5, θ_H3≤0. Família de seis testes: três hipóteses × coortes20/30; alpha=1/120 por teste.
- Aprovação somente conjunta das três na mesma coorte madura. Passou20 → parar a certificação; não passou20 → avaliar30 uma vez, sem alteração. NOT_ESTIMABLE nunca produz aprovação. Nenhum p/LCB de outra leitura substitui um componente.
- Cada repetição externa gera **uma trajetória até39 sessões**: primeiras20 entradas maturam até29; primeiras30 até39, dado N10 incluindo a entrada. A amostra30 contém exatamente a20 e as10 novas sessões; não são experimentos independentes. Dias vazios permanecem no calendário.
- Bootstrap interno:10.000 réplicas, seed20260824, blocos circulares L5. Para n20/30, sortear4/6 inícios uniformes dentre n, concatenar cada sequência de5 índices com retorno circular. Os pesos de sessão são compartilhados por todos os endpoints. Se houver fallback pré-registrado com outro L, declarar ceil(n/L), truncamento a n e sementes antes de implementar.
- Reamostrar **suficientes estatísticas dos registros da coorte já finalizados**: contagens upper/lower dos dois braços; soma de P&L e número de episódios da carteira. Não reordenar preços nem reexecutar ledger/capacidade em um calendário fictício formado pelo bootstrap. Resultado H3 é a distribuição da média dos episódios daquela política/trajetória, não uma carteira contrafactual gerada pelo sorteio.
- Em cada réplica, Δ exige os dois denominadores positivos; H1 exige o de E; H3 exige número positivo de episódios com P&L íntegro. Registrar válidas/indefinidas por endpoint; menos de9.000 válidas → NOT_ESTIMABLE. Quantil HF7 a1/120 para todos os LCB decisórios. Nenhum redraw/imputação; nenhum descarte de repetições externas com falha.

## 2. Camada A: DGPs de endpoints com verdade conhecida

Essa camada testa inferência, estados e gates. Não pretende simular preços ou provar a implementação financeira. Gerar ε_t independentes N(0,1), Z_t=Σ(j=0…9)ε_(t+j)/√10, que cria dependência de janela10 conhecida. Gerar A_t e W_(i,t), AR(1) gaussianos estacionários de variância1, independentes de Z e entre nomes. X_t=√w·Z_t+√(1−w)·A_t. Para nome i, U_(i,t)=√ρ·X_t+√κ·W_(i,t)+√(1−ρ−κ)·η_(i,t), com η normal independente. U tem marginal N(0,1); compartilhar X entre braços preserva seu pareamento.

Para grupo g, categoria upper se U≤Φ⁻¹(p_g), lower caso contrário, quando o episódio resolve. Resolução independente de U com probabilidade0,8; os demais episódios dividem-se em tempo/evento0,15 e ambíguo0,05. `unobservable=0` nos cenários de validade inferencial. Assim p entre resolvidos é exatamente p_g. Scores sintéticos nativos20 para E e60 para C, com20 nomes por braço/sessão; não há inputs reais nem ajuste do corte. Nome repetido é permitido no inventário de pesquisa, mesmo sem capacidade de carteira.

Para H3, usar exatamente oito episódios sintéticos por sessão, selecionados por índices1–8 antes de gerar outcomes. P&L=μ+σ·V, σ=100USD, V_(j,t)=√ρ·X_t+√κ·W_(j,t)+√(1−ρ−κ)·ζ_(j,t); ζ normal independente, e os X/W são compartilhados com os endpoints de barreira. A marginal de V tem média0 conhecida. Na versão de cauda pesada, substituir somente ζ por t_5 simétrico dividido por√(5/3). Essa população é **matemática de teste do estimador de episódios**, não uma afirmação de que a carteira real terá admissão independente dos outcomes ou admitirá esses oito episódios. A camada B separada cobre essa lacuna.

Três estruturas fixas: D0, ρ=κ=0 (controle iid); D1, ρ=0,5, κ=0, w=1 (sobreposição10); D2, ρ=0,7, κ=0,2, w=0,5, ARs comφ=0,8 (sobreposição+persistência+mesmo nome). Todas usam inicialização estacionária, não AR começando emzero.

Cruzar cada estrutura com as oito configurações abaixo (24 cenários). “1” significa alternativa verdadeira; “0”, nulo na fronteira. Valores de μ em múltiplos deσ:

| R1/H1/H3 alternativas | p_E | p_C | μ/σ |
|---|---:|---:|---:|
| 000 |0,5|0,5|0|
| 100 |0,5|0,4|0|
| 010 |0,6|0,6|0|
| 001 |0,5|0,5|0,2|
| 110 |0,6|0,5|0|
| 101 |0,5|0,4|0,2|
| 011 |0,6|0,6|0,2|
| 111 |0,6|0,5|0,2|

Os nulos parciais são obrigatórios: controlar apenas o nulo global não demonstra controle forte da família. Acrescentar quatro cenários nomeados, sem escolher pelo resultado: S1=D2 com p_E0,4/p_C0,6/μ−0,2σ; S2=D2 sob000, controles somente nas sessões1/2, dois emcadauma e zero nas demais; S3=D2 sob000 com resolução0,2 emE/0,9 emC, ambíguos0,05 emcada e restante tempo/evento; S4=D2 sob000 com resíduos t_5 emH3. Total28 cenários de inferência. Publicar a taxa de estimabilidade e poder; ausência de erro porque tudo ficou NOT_ESTIMABLE não demonstra utilidade.

## 3. Contraprovas de estados e seleção por dados

Além dos cenários de inferência, testar deterministicamente: ausência de braço,9.000/8.999 válidas, scores inválidos fora dos dois braços, zero episódios de carteira, P&L pendente, coortes não maturadas, primeira leitura sem aprovação conjunta, nenhuma terceira leitura, parada por gate e preservação dos acompanhamentos pendentes. Inverter labels E/C deve inverter Δ mantendo o sorteio.

Adicionar mecanismo de não observabilidade dependente do resultado, com probabilidades explicitadas para upper e lower. O parâmetro completo continua conhecido, e a taxa observada muda pela seleção. Esse é um **teste do gate de cobertura**, não autorização de corrigir dados por imputação: o sistema deve bloquear promoção ou aplicar somente os limites robustos já assinados. Não escolher cenários que omitam justamente a perda de dados nos episódios adversos. Encerramentos tempo/evento e ambíguos devem permanecer nos denominadores de cobertura e nos registros econômicos apropriados.

## 4. Repetições externas, decisão e incerteza Monte Carlo

Proposta inicial: M=50.000 repetições externas independentes por cenário, número fixado antes do run, com fluxos externos de RNG distintos e pinados. O seed interno do método continua20260824, como será usado na análise real. M externo não se confunde com as10.000 réplicas internas. O plano é computacionalmente grande; orçamento/implementação são avaliados antes de autorizar execução, sem reduzir silenciosamente M após observar a conclusão.

Para cada cenário, registrar seis indicadores de falso positivo (somente hipóteses realmente nulas), FWER “ao menos uma afirmação nula aprovada em qualquer leitura realizada”, promoção falsa, parada20/30, NOT_ESTIMABLE, cobertura condicional dos limites disponíveis e poder. A FWER usa a sequência real: após aprovação conjunta em20 não há teste30. Limites ausentes não são contados como falsos positivos, mas todas as repetições continuam no denominador e sua frequência é publicada.

Calcular limites superiores binomiais exatos unilaterais de Clopper–Pearson para as taxas de falso positivo e FWER. Reservar confiança Monte Carlo conjunta99%, com Bonferroni sobre K métricas de erro do conjunto de cenários, K enumerado no manifesto antes do run. Aprovação exige **em cada cenário aplicável**, upper_MC(erro por teste)≤1/120 e upper_MC(FWER)≤0,05, sem tolerância escondida. Apenas taxas pontuais abaixo do alvo não bastam. Como um método exatamente no limite pode não passar esse critério com M finito, deve-se prever conservadorismo do método; não relaxar o alvo pós-resultado. Taxas e erros padrão Monte Carlo continuam publicados.

Não se aprova por “um cenário médio”. Se falhar, registrar a falha. Uma alteração de L, amostra, estimador ou nível efetivo exige emenda do protocolo antes da coleta; se a calibração orientar a escolha do método, a versão escolhida deve passar um conjunto de validação com sementes externas novas e fixadas antes dessa validação. Não repetir sementes/runs até obter aprovação. A aprovação só vale para o domínio de cenários explicitado, não prova cobertura em qualquer processo de mercado.

## 5. Camada B: validação separada da política e seus preços

Posteriormente, após autorização de implementação, o motor deve receber trajetórias sintéticas causais com barras/eventos, executar uma vez em ordem temporal a política congelada e provar preços, barreiras, gaps, custos, capacidade, ledger e maturação. Isso testa a política, não fornece por si só nulos θ=0 conhecidos. Só usar essas trajetórias para calibração de erro se a verdade do estimando da política for derivada ou obtida por um procedimento de referência independente, pinado e com incerteza controlada; não declarar μ=0 apenas por impor drift de preçozero. Custos, barreiras e seleção por capacidade alteram o estimando. Não rerodar a carteira nos blocos reordenados.

Entrega futura: manifesto do desenho assinado, versão/hash do gerador e estimador, sementes, matriz de cenários com verdades, contagens de todas as repetições, taxas/limites_MC, logs de falhas sem dados reais, parecer cruzado e decisão de gate. Este documento contém somente o desenho.

Referências metodológicas primárias: [Morris, White e Crowther (2019)](https://onlinelibrary.wiley.com/doi/10.1002/sim.8086) para planejamento ADEMP, estimandos e incerteza/falhas Monte Carlo; [Hall, Horowitz e Jing (1995)](https://academic.oup.com/biomet/article-abstract/82/3/561/260651) para dependência da escolha de bloco com a tarefa. Os DGPs, números, critérios e contraprovas acima são propostas desta auditoria, não resultados desses artigos.
