# Adendo E — erratas e precedência da spec V2 V1 revisão 2

Objeto: texto da revisão 2 SHA256 `175aa499d9b21a996c4bf603ce7241d2958a954d601673e0821fc5fa63a73494` e anexos A–D, incluindo o fechamento de B, identificados no manifesto desta entrega. Este adendo integra o conjunto documental assinado pelo Codex. As assinaturas de Fable e Dudu devem se referir ao mesmo conjunto; nenhuma assinatura anterior é transferida automaticamente a ele.

## E1. Integridade dos dados

No §2.3, substituir a expressão “dados insuficientes/íntegros ou ATR ≤ 0 → inelegível” por:

**“Dados insuficientes ou não íntegros, ou ATR ≤ 0, tornam o candidato inelegível, com o motivo contado.”**

Dados íntegros não são causa de rejeição. A normalização do ATR continua a usar somente splits conhecidos e efetivos até a decisão, conforme a disponibilidade causal do §2.1 e o anexo A3.

## E2. Dimensionamento da calibração

No §9, item 2, a expressão “ensaio de custo da calibração antes de fixar M definitivo” deve ser lida como:

**“Ensaio de custo para aferir a viabilidade computacional de M = 50.000 repetições externas por cenário. M permanece fixado neste conjunto; qualquer alteração exige emenda assinada antes da calibração certificadora. O ensaio de custo não gera veredito de calibração.”**

Mantêm-se as 10.000 réplicas internas, os 28 cenários, as sementes, K = 121 e os critérios de erro descritos no contrato. O rito continua: assinaturas do conjunto → implementação e auditoria do código → calibração sintética e aceitação do laudo → coleta pelos gates. Nada neste adendo afirma que o custo foi medido ou que a calibração já passou.

## E3. Precedência documental

Em divergência explícita, aplicam-se, nesta ordem: este adendo E; o texto principal da revisão 2; o fechamento `FECHAMENTO_ANEXOS_PROPOSTA_CODEX.md`; os anexos A/B nos seus respectivos objetos; os anexos C/D como bases e parâmetros complementares. A falta de repetição de um detalhe no resumo principal não revoga uma definição complementar compatível dos anexos.

O fechamento de B prevalece sobre a proposta B nos pontos que define. C é preservado pelos parâmetros da candidata compatíveis com a revisão 2; D, pela candidata R1 assinada, seu corte e semântica. Os trechos anteriores sobre leituras 15/20, sorteio independente por sessão e admissão global por hash são substituídos pelas definições atuais: coortes 20/30 com maturação 29/39; estimador circular L = 5 a avaliar; admissão causal por disponibilidade com hash somente nos empates. As referências ao M1/net0 permanecem contexto histórico, sem impor sua certificação à V2.

## E4. Escopo da assinatura

O DE ACORDO do Codex vale para o **manifesto que contém a revisão 2, os cinco arquivos dos anexos A/B/fechamento/C/D e este adendo E**. Não é assinatura isolada do texto principal sem estas erratas. O manifesto fornece nomes locais, origens e hashes para localizar todos os arquivos, sem depender dos caminhos relativos abreviados do §8.

Trata-se de aprovação documental do desenho e do protocolo de avaliação. A adequação de L = 5, o desempenho da candidata e o realismo da execução modelada ainda dependem das verificações prescritas. Não há autorização de implementação, coleta ou deploy antes das três assinaturas do conjunto, nem promoção automática a paper depois de uma leitura estatística.
