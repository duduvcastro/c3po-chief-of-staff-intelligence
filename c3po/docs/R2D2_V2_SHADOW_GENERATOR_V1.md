# Gerador shadow V2 — implementação para auditoria, desativada

Esta implementação corresponde ao manifesto assinado
`01d258903c060660a51ad48e7506903d038b0fa6901142456e06c7858350c359`
da spec V2 V1 revisão 2 e adendo E. O parecer e as assinaturas estão na
[#348](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/issues/348#issuecomment-5561678194).
A emenda 1 está em revisão separada; seus parâmetros de 40/60, lista limitada
e método t não foram incorporados a este código. O exportador do contrato
vigente usa 20/30, maturação 29/39. Mudar o contrato exige novo manifesto,
adaptação auditada e nova época. O estimador/calibrador está na PR #381 e não
é importado nem executado pelo coletor.

## Entrega e fronteiras

O processo `app.r2d2_v2_shadow_worker` lê evidências privadas, fixa a primeira
resposta completa de cada nome em `[10:00:00,10:01:00)` de Nova York, aplica os
filtros assinados e registra a pesquisa em ambos os braços. Uma carteira
virtual separada admite somente ELIGIBLE, preservando as observações CONTROL
e os episódios que não cabem na carteira. Os eventos corporativos, preços,
intenções e saídas têm trilha privada. Toda execução é hipotética; preço
demonstrado não é ordem executada.

Não há ligação com `main.py`, os objetos de trading, o worker V1 ou rotas de
BUY. Nenhuma posição, ordem, controle V1 ou `entries_paused` é lida/alterada.
O worker não chama `Database.initialize()`, pois essa rotina também executa
backfills de outros módulos. As duas tabelas da migração
`045_r2d2_v2_shadow.sql` são próprias da V2; a migração não foi executada em
produção nesta entrega. Não há serviço novo no compose, automação ou deploy.

## Modos e autorização de execução

- OFF é o padrão (`C3PO_R2D2_V2_SHADOW_ENABLED=false`). Não abre arquivo,
  conexão de banco ou provedor. `--capabilities` também não abre banco.
- DIAGNOSTIC usa época própria e grava universo, inputs congelados, tentativas
  e motivos. Não cria ledger, episódio, carteira ou outcome, não lê a fita de
  eventos e não inicia relógio de coorte. Essa época não pode ser promovida nem
  reaproveitada como coorte certificadora.
- CERTIFIED é apenas o nome do caminho que **exige liberação após calibração**;
  não é um veredito do coletor. Requer código auditado, fontes auditadas e
  calibração ACCEPTED. Nenhum recibo de liberação acompanha esta PR. O smoke
  do método vigente reprovou; portanto não há liberação certificadora atual.

Para uma execução futura autorizada, o operador controla um arquivo privado
`R2D2_V2_RELEASE_V1`, com os seguintes campos:

| Campo | Exigência |
| --- | --- |
| `schema`, `manifest_sha` | Schema exato e manifesto acima |
| `epoch` | Prefixo `R2D2-V2-SHADOW-`, identidade nova por liberação/modo |
| `mode` | DIAGNOSTIC ou CERTIFIED |
| `first_session`, `approved_at` | Sessão oficial declarada antes da abertura; aprovação causal |
| `code_revision` | SHA Git completo, igual ao `C3PO_BUILD_SHA` em execução |
| `code_audit_sha`, `authorization_ref` | Hash do parecer e referência da ordem/delegação |
| `source_audit_sha` | Obrigatório no caminho CERTIFIED |
| `calibration_sha`, `calibration_status` | Hash do laudo e ACCEPTED no caminho CERTIFIED |

O SHA256 dos **bytes** do arquivo é fixado em
`C3PO_R2D2_V2_SHADOW_RELEASE_SHA`; o caminho fica em
`C3PO_R2D2_V2_SHADOW_RELEASE_FILE`. O arquivo é privado, regular e não symlink.
O recibo é uma atestação operacional cujo conteúdo deve ser conferido no rito;
o hash detecta troca de bytes, não autentica sozinho assinaturas externas.
Mesmo manifesto/modo com outro recibo requer época nova. Falta, troca de
hash/revisão ou erro de integridade interrompe o processo, com rollback da
observação corrente. Não há fallback em memória quando habilitado.

O caminho de dados é `C3PO_R2D2_V2_SHADOW_SOURCE_DIR`. O processo independente
futuro é `python -m app.r2d2_v2_shadow_worker`; `--once` executa uma única
observação autorizada. O intervalo configurado é 1 segundo (0,25–5 segundos).
**Essas instruções não são ordem de ativação.** O único comando de inspeção
que independe de liberação é `python -m app.r2d2_v2_shadow_worker --capabilities`.

## Causalidade e pesquisa

O produtor fornece os timestamps originais. O coletor registra novamente o
relógio real após leitura e aquisição do lock do banco: demora de I/O não
cria uma decisão fictícia dentro da janela. Cotação velha é reavaliada nesse
instante. Inputs completos inválidos, inclusive risco null, ficam congelados;
não ganham segunda tentativa por mudança de elegibilidade. Cotação ainda
ausente pode completar dentro da janela; no encerramento sua ausência é contada.

Calendário XNYS via exchange_calendars, com versão e hash por sessão, define
61 sessões prévias, dez sessões de horizonte incluindo a entrada e fechamento
oficial (inclusive dias curtos). ATR14 é Wilder em 60 TRs; ADV20 usa turnover
bruto das últimas vinte sessões. Não existe adjusted_close ou fallback de risco.
O corte é `44.10596901963097`, sem arredondamento ou conversão de texto/bool.

O universo observado é fixado na primeira resposta com cobertura verificada
da janela. Mudança posterior é registrada, sem adicionar nomes escondidos.
Este comportamento é o contrato atual; não implementa a lista D−1 proposta
na emenda. Identidade de nome é `US:SYMBOL`, inclusive após transferência entre
NYSE e Nasdaq. O hash de desempate é literalmente
`SHA256(epoch + '|' + data_sessao + '|' + simbolo)`, só para disponibilidade
simultânea; a sequência de admissão fica no journal.

As duas populações da pesquisa usam uma ação por episódio e identidade por
nome/data. A carteira aplica custos, risco de 0,02% do NAV, caps, caixa,
restrições por nome e perda diária. Bloquear carteira por cobertura não apaga
pesquisa; N/D nunca se converte em zero. A6 é modelagem explícita de fill de
barreira; ambiguidade em pesquisa não recebe silenciosamente o stop-first
conservador usado na carteira. Fonte tardia não reescreve caixa já registrado.

## Evidências, observabilidade e armazenamento

O [contrato do data port](R2D2_V2_DATA_PORT_V1.md) especifica envelopes,
timestamps e amostras sintéticas. Esse port é I/O real para produtores
separadamente auditados; não é um adaptador pronto dos feeds legados.

O estado e os registros de uma observação são confirmados na mesma transação
PostgreSQL, com lock por época, versão, SHA do estado e journal encadeado por
hash. IDs repetidos com mesmos bytes são idempotentes; conteúdo diferente
para o mesmo ID é erro. Um lote de ledger copia/valida o estado uma vez;
erro invalida o lote e a transação não publica resultados parciais.

Ruptura de sequência de eventos, intervalo ausente de barras, falta de fonte
ou evidência de negócios desatualizada gera DATA_GAP. Cotação/MARK fresca
não substitui cobertura de negócios para verificar barreiras. A tolerância
de 90 segundos é de transporte para barras de um minuto, **não** extensão da
janela de entrada, do horizonte ou da regra de idade <=10s das cotações.
Ela não permite pular um intervalo de barra: um buraco declarado bloqueia
imediatamente. Um trade que fecha episódio não apaga hiato anterior.

O preço do arquivo preserva `source_available_at`; o ledger usa o recebimento
pelo coletor. Os relógios de sessão vêm do calendário, não de arquivos externos.
Depois das trinta datas programadas de entrada, os episódios/recebíveis
pendentes continuam monitorados, inclusive para registrar breach do horizonte.
Todos os dias programados, com zero elegíveis ou processo indisponível, ficam
representados. Campos públicos são agregados e hashes; IDs/inputs/fita são privados.

## Interface com o estimador

`export_cohort(state, size, now=..., calendar=...)` exige modo CERTIFIED, tamanho
20/30 e maturação no fechamento da sessão29/39. Não calcula bootstrap nem
veredito. `--export-cohort 20 --output <arquivo_novo>` grava resultado privado
0600 sem substituir arquivo existente. O export contém manifesto, liberação,
época, revisão, calendário, datas, hash, veto e gate de cobertura.

Cada sessão programada contém `arms.ELIGIBLE/CONTROL` com as cinco categorias,
episódios e pendentes, `portfolio_pnl_usd_sum`, `portfolio_episode_count`,
`portfolio_pnl_indeterminate_count`, `data_gate_unknown`, `finalized` e
`capture_coverage_unknown`. Soma de P&L fica null se algum episódio necessário
não tiver resultado identificado; seu denominador continua presente. O
adaptador do estimador deve rejeitar gate fechado/null, nunca convertê-los em zero.

Nenhum adaptador para a API da #381 é ativado nesta entrega. Mudanças de
coortes/estimando pela emenda exigem novo schema/revisão e auditoria conjunta,
preservando a época original.

## Dependências para ativação

O diagnóstico de fontes foi publicado em
[#348](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/issues/348#issuecomment-5561835978):
o cache de quotes perde lados/recebimento; o diário legado descarta OHLC e
pode usar adjusted_close; não há calendário prospectivo de earnings com
cobertura verificável. Só esses objetos atuais produziriam zero elegíveis.
Não houve consulta a provedores nem conclusão sobre seus planos/entitlements.

Antes de qualquer coleta ainda faltam os produtores, seus recibos de cobertura,
auditoria cruzada, calibração aceita e ordem/liberação. Antes de ligar o modo
DIAGNOSTIC faltam seu produtor de inputs/lista, auditoria e ordem própria.
Também são portões operacionais: integração em PostgreSQL real, dimensionamento
da época/journal, teste de carga com o universo previsto e o protocolo auditado
de retenção/ACK do spool. Não existe ACK ou remoção automática de arquivos
neste port; atingir 4096 arquivos de evento bloqueia a leitura, sem descartar
evidência. O estado JSONB e seu índice de idempotência crescem durante a época;
um microteste local não demonstra capacidade para todo o programa.

Os testes são sintéticos: calendário real de biblioteca, inputs/quotes/barra,
carteira, fonte privada, reinício, rollback, concorrência32, namespaces,
ausências, janela, modos e contraprovas de causalidade. O protocolo SQL foi
verificado com spy transacional; não havia PostgreSQL/Docker local e não se
conectou a banco externo. Esse limite faz parte da entrega para auditoria.
