# Aprovação restrita do CI de remediação

A capacidade é opt-in. Ausência de `automatic_ci_approval`, `false`, strings e
outros valores não habilitam aprovação. O instalador e a configuração versionada
continuam sem ativá-la. A configuração explícita, em uma instalação futura
autorizada pelo dono, seria `"automatic_ci_approval": true` no arquivo de política
já usado pela rotina. Preparar ou mesclar o código não autoriza essa ativação,
mudança de credenciais/permissões ou qualquer operação no host.

A aprovação usa também os gates existentes: `automatic_merge` precisa estar
habilitado, dentro de 10:00–12:00 UTC, sem hold, ensaio protegido, reboot em curso
ou falha de evidência/saúde. A saúde é conferida antes da última leitura de
relógio/hold/trial. Isso não altera a janela nem a política de merge.

A rotina considera somente PRs abertas, não draft, para `main`, do mesmo
repositório e de `github-actions[bot]`, nas branches
`automation/dependency-security-*` e `automation/container-security-rebuild-*`.
Compartilha as validações de conteúdo da promoção: dependências só nos cinco
arquivos de `ALLOWED`, com alterações reproduzíveis dos avisos atuais; rebuild
somente em `c3po/security/container-rebuild-trigger.json`, consistente com os
achados reais atuais. Renames, arquivos extras, fixtures e alterações de código
não entram nessa autorização.

Uma execução separada por `workflow_dispatch` de `c3po-pipeline.yml` deve ter
concluído com sucesso no head exato. A tentativa exata deve ter todos os jobs
obrigatórios verdes, inclusive `Security remediation proof`. Essa prova já
amarra `ref` ao SHA e exige `remediation=true`, `deploy=false`. Não se aprova a
própria prova bloqueada nem se aceita prova de um head anterior.

Os únicos workflows de destino são `c3po-pipeline.yml` e `backend-postgres.yml`,
evento `pull_request`, com identidade de workflow/repositório/branch/SHA
conferida. `action_required` normalmente aparece na **conclusão** de uma execução
com `status=completed`. Se `pull_requests` vier vazio, a associação do commit
com PRs deve retornar exatamente uma PR correspondente, usando paginação completa.
A rotina reconsulta conteúdo e prova/tentativa; após a prova e a sondagem de
saúde, faz as últimas consultas de run, associação, `main` e PR. Só então confere
novamente janela/hold/trial, sem outra sondagem longa, antes do pedido.
O endpoint não oferece uma operação atômica que vincule aprovação ao head
mutável da PR; a aprovação permanece limitada ao run identificado e nunca é
tratada como permissão para merge.

O único pedido novo é `POST /actions/runs/{id}/approve`. Resposta HTTP 201 sem
corpo significa pedido aceito, não CI verde. Não há fallback para rerun,
dispatch, aprovação de ambientes, revisão de segurança pela interface web ou
merge. Um ciclo que pede aprovação termina essa fase e aguarda evidência nova.

Antes do POST, o relatório grava e sincroniza intenção identificada por
`run_id`, `run_attempt` e `head_sha`. Nenhum resultado ambíguo é reenviado
automaticamente para essa mesma identidade. Timeout, 403/404, HTTP inesperado ou
corpo inesperado mantêm a situação sem confirmação, com erro sanitizado e gate
fechado; ciclos posteriores reconciliam somente por GET. Um run ainda em curso
fica pendente; falha permanece falha. A prova mais recente não pode ser
substituída por uma tentativa verde anterior.

Os recibos ficam em `ci_approval.history`, sem tokens ou corpos de erro. A rotina
preserva essa intenção mesmo se o ciclo falhar após o POST. Mudança do head ou
fechamento da PR aposenta o recibo histórico, com motivo, sem reescrever sua
conclusão como sucesso. Uma tentativa posterior é acompanhada até terminar ou
exigir outra aprovação; cada tentativa tem identidade própria. Um run novo do
mesmo workflow/SHA pode aposentar um recibo antigo após associação inequívoca
com a PR: deve estar verde ou exigir aprovação. Uma execução nova falha não
apaga a falha anterior. O recibo preserva o resultado original do POST e a
conclusão observada, além da identidade da substituição. O histórico tem
limite de 100 recibos e bloqueia novos pedidos quando cheio, sem descartar
silenciosamente resultados incertos. Manutenção desse limite exige uma decisão
operacional futura.

O relatório continua no schema `C3PO_SECURITY_AUTOMATION-v1`. Aprovação aceita
acrescenta espera e bloqueador de saúde; resultado incerto ou CI com falha entra
em `errors`. O watchdog e a governança não recebem uma falsa conclusão saudável.
Desabilitar o opt-in impede novos POSTs, mas a reconciliação de intenções já
gravadas continua sendo somente leitura.

GitHub documenta o gate de workflows de PRs criadas pelo `GITHUB_TOKEN` em
[GITHUB_TOKEN](https://docs.github.com/en/actions/concepts/security/github_token)
e no [anúncio de 11/06/2026](https://github.blog/changelog/2026-06-11-bot-created-pull-requests-can-run-workflows-if-approved/).
A página REST de [aprovação de workflow](https://docs.github.com/en/rest/actions/workflow-runs#approve-a-workflow-run-for-a-fork-pull-request)
ainda usa o título de PR de fork e requer Actions/write. O gate same-repository
foi observado por GET na PR #476; a aplicação desse POST ao caso concreto não
foi executada nesta alteração. Uma retenção por workflow suspeito que exija
revisão autenticada pela interface web continua exigindo intervenção humana.
