# Rotina diária de segurança do C3PO

Solicitação do Dudu em 12/09/2026: verificar diariamente as vulnerabilidades,
procurar correções publicadas, corrigir quando houver uma atualização compatível
e verificar o funcionamento depois. A execução é por software no servidor e no
CI, sem chamadas a modelos de IA. A fiscalização diária adicional do Codex não é uma dependência da execução.

## Cobertura e horários

* **Ubuntu:** `apt-daily-upgrade.timer` e unattended-upgrades já instalados aplicam
  diariamente somente atualizações dos canais de segurança. Snapshot local a cada
  15 minutos; healthchecks de início, sucesso e falha. Reinicializações necessárias são solicitadas automaticamente pelo controlador na janela de 07:00–09:00 BRT e verificadas após a volta. O unattended-upgrades mantém seu reboot próprio desabilitado: existe um único controlador de reinício.
* **Repositório:** o timer `c3po-security-daily.timer`, no host, consulta os avisos
  abertos do Dependabot; o CI também executa `pnpm audit` diariamente, independentemente da entrega dos alertas pelo GitHub. Avisos adicionais são deduplicados por pacote/GHSA e entram no painel. Após 07:00 BRT, uma vez por dia e após novo deploy, dispara
  `dependency-security.yml`. Além disso, no primeiro ciclo que vê uma nova main
  (`last_dispatched_main`), redispara somente `dependency-security.yml`, a qualquer
  hora, para regenerar a auditoria npm dessa revisão. A credencial permanece no host; a exportação contém
  somente avisos, nomes de pacotes e versões corrigidas públicas.
* **Imagens:** reutiliza o scanner Trivy diário existente e dispara nova varredura
  após cada deploy. As imagens são exportadas e examinadas fora do servidor.
* **Conclusão:** o timer reconcilia resultados às HH:10 (com até 30s de atraso), sem
  novo scan pesado quando já solicitado no dia. Governança atualiza o atestado no
  máximo a cada hora, inclusive após a instalação automática de pacotes do host.

## O que pode ser corrigido automaticamente

O preparador aceita versões estáveis publicadas como correção no aviso: dependências
diretas npm, overrides pnpm já existentes e requisitos Python simples com faixa
preservada. Não altera scripts de instalação, código, compose, credenciais ou flags.
Não atravessa versões maiores; para versões 0.x também preserva a versão menor.
Dependência transitiva sem override, restrição complexa, troca de major, troca de
digest e aviso sem correção ficam registrados para intervenção. A disponibilidade
da correção é consultada novamente no dia seguinte.

Existe uma única PR de dependências, em branch do bot, atualizada com lease.
Rebuilds de imagens usam as PRs do controlador existente; somente o arquivo de
trigger pode mudar para promoção automática. Fixtures de dry-run são excluídas.

O host só promove uma PR do bot do próprio repositório se:

1. Main e a revisão implantada forem iguais e nenhum pipeline estiver em execução.
2. As alterações forem reproduzíveis a partir dos avisos atuais (ou do trigger
   factual de imagens), sem arquivos adicionais.
3. O último pipeline do SHA exato tiver passado testes de backend, type check,
   frontend, secrets e scan sem ocorrências corrigíveis; dependências npm também
   passam auditoria dos avisos após a correção. O job de prova exige ref imutável,
   `remediation=true` e `deploy=false`.
4. A proteção estrita de main e sua aplicação a administradores estiverem ativas.
   O controlador não contorna exigências de revisão nem regras do GitHub.
5. Forem 07:00–09:00 BRT e `/etc/c3po/security-maintenance.hold` não existir.
   Disponibilidade do host e janela são reconferidas imediatamente antes do merge.

O merge inicia o deploy normal, com portão de saúde e rollback de imagens já
existentes. Novo scan de produção e atestado são obrigatórios: PR mergeada, build
verde ou aviso fechado no GitHub isoladamente não significam host corrigido.
Se o deploy falhar, main e implantado divergem e outra promoção fica bloqueada.

Não há garantia de corrigir todas as falhas no mesmo dia: ausência de patch,
incompatibilidade, CI vermelho, trabalho em andamento ou freeze são pendências visíveis,
nunca convertidas em zero nem escondidas como “Atualizado”.

## Reinicialização e fiscalização permanentes

A autorização de Dudu em 12/09 inclui implantação, execução permanente e reboot
necessário após atualizações. O reboot usa `/var/run/reboot-required`, janela
07:00–09:00 BRT e hold explícito. Adia se houver pipeline ativo, apt em execução,
transação ativa ou ingestão marcada como running iniciada durante a vida dos contêineres atuais. Registros históricos anteriores a todos os contêineres não são alterados. O último horário para solicitar reboot é 08:45 BRT, reservando tempo para a volta. Obtém os locks reais do dpkg e
o lock compartilhado com o deploy. A janela/hold são reconferidos antes do pedido.
Raízes de ensaio com data atual/futura ou lock histórico de probe ocupado impedem a manutenção; recibos históricos retidos não criam suspensão perpétua. O watchdog aplica a mesma janela antes de iniciar serviços. Um recibo durável contém o boot_id anterior. O marcador volátil impede que um
deploy comece entre o pedido e a parada. No máximo um pedido a cada 24 horas;
reboot não ocorrido em 15 minutos é falha visível, sem loop de reinicialização.

Após o boot, o watchdog verifica boot_id diferente, ausência de reboot-required,
API, web e SELECT 1 no banco. Se necessário, inicia somente os contêineres já
existentes de db/api/web, preservando imagens, configuração e workers pausados.
Não faz rollback de banco nem tenta corrigir um host que sequer consegue iniciar.

`c3po-security-watchdog.timer` roda aos minutos 05 e 35 e três minutos após o boot.
Recupera timers desabilitados/parados e solicita novo ciclo se o recibo faltar,
estiver velho ou tiver falhado. O workflow externo `security-watchdog.yml` faz
nova conferência diariamente às 09:35 BRT, por SSH pinado; detecta inclusive a
interrupção do watchdog local. Falha de SSH ou validação falha o workflow.
Todos os agendamentos são permanentes, sem data de término. Ausência de correção
ou incompatibilidade permanece visível e volta a ser consultada diariamente.

## Instalação e ativação

O deploy instala/atualiza os scripts e unidades versionados após o portão de saúde,
com `sudo bash scripts/install-security-daily.sh`. A primeira instalação cria um
hold antes da política e dos timers. Após a aceitação, o executor autorizado remove
somente o hold de bootstrap e registra a ativação, sem nova autorização do dono.
A política autorizada inclui automatic_reboot. Atualizações preservam configurações
locais e todo hold explícito. A credencial já configurada na API precisa ler
Dependabot/Actions e escrever dispatches/merges; falhas nunca significam zero avisos.
Não há credencial de provedor no controlador nem chamada de mercado.

Para manutenção especial, criar `/etc/c3po/security-maintenance.hold`: suspende
promoções, reboot e recuperação de timers. Consultas continuam. Para pausar toda
a rotina, criar o hold antes de desabilitar os dois timers. Nunca reativar timers
datados de ensaios anteriores. A revisão D14 precisa ser reconciliada com Fable
após esta implantação; esta rotina não concede execução de ensaio/captura.

Uma release CERTIFIED instalada em `/mnt/day-d-data/r2d2-v2-release-*.json` ou
um marcador `/mnt/day-d-data/.r2d2-v2-pinned` também veta manutenção e recuperação,
inclusive antes da primeira sessão e entre sessões. O rito de encerramento
arquiva a release fora desse diretório ativo e remove o marcador somente depois
de comprovar o encerramento da época. A rotina de segurança não declara uma época
terminal nem remove esses arquivos; após o encerramento, retoma automaticamente.
JSON inválido ou symlink bloqueia. A release DIAGNOSTIC válida é distinguida de
CERTIFIED. Até existir protocolo aprovado de revisão por hashes dos módulos,
atualizações que exigem deploy ficam pendentes durante a época CERTIFIED ativa.

## Evidência e falhas

`runtime/security/security-automation-report.json` é escrito atomicamente, com
SHA-256 e horário UTC. Preserva pendências, reboot, hashes dos scans, revisão
implantada, dia do último dispatch e o resultado da promoção. Erro de leitura,
credencial, parser ou consulta não produz um relatório saudável. Relatório ausente
ou antigo aparece no painel; falhas geram notificação de job pelo mecanismo existente,
deduplicada por dia. A disponibilidade do worker de governança continua coberta
pelo seu healthcheck externo existente.

Auditoria npm íntegra e recente (< 26h), mas de uma revisão anterior, é registrada
em `pending` (`npm_evidence_pending`, status `waiting_npm_evidence`), não em `errors`,
somente até 3h desde o primeiro ciclo com defasagem (`npm_lag_since`, mantido mesmo
que a main mude de novo e zerado só por auditoria da main atual), com o redisparo
já solicitado para a main atual e sem falha na última execução de
`dependency-security.yml`. O relatório nunca fica saudável, promoção e reboot seguem
bloqueados como com evidência ausente, e os avisos conhecidos da auditoria anterior
continuam no relatório (critical/high npm mantêm a governança em falha). Sem
critical/high, a governança mostra atenção ("evidência npm pendente pós-deploy
(regenerando)") sem notificação de falha de job. Fora dessas condições, inclusive
com âncora futura ou inválida, é o erro `npm_evidence_unavailable`; `pending`
malformado é tratado como falha.

Validação de aceitação em produção: timer habilitado, primeiro ciclo registrado,
permissões do token conferidas, PR/CI/merge controlado na janela e scan posterior
mostrando os avisos resolvidos. Não executar esse ensaio durante o D14.

## Relatório read-only de incidentes

`.github/workflows/ops-readonly-report.yml` roda às 06:30 e 11:30 UTC (03:30 e 08:30 BRT; ver "Varredura noturna de saúde") e por
`workflow_dispatch`. Pelo transporte SSH do deploy, executa
`python -m app.operational_incidents --report-json` dentro do contêiner `api` em execução
(`docker compose exec -T`, sessão PostgreSQL com `default_transaction_read_only=on`, nada
copiado, criado ou reiniciado no host; reboot de segurança pendente adia o relatório). O
módulo só lê o ledger de incidentes e os cartões **locais** do painel de saúde
(governança, incidentes e controles Day D/valuation: linhas do banco e arquivos de
evidência); as sondas externas e o ping de healthcheck nunca rodam.

A saída é só agregada: incidentes abertos/reconhecidos agrupados por tipo
(`governance-vulnerability`, `notification:job_failure`, `notification:disk_threshold` ou
`other`), origem, severidade e estado, com quantidade, idade do episódio atual (abertura
ou reabertura → agora), quantos passam de 24 h e a última observação; e os cartões
vermelhos/âmbar por chave fixa. Chave do incidente, título, detalhe, evidência, ator e
texto dos cartões nunca saem do processo. No runner, o verificador exige o esquema exato
(chaves e vocabulário fechados, horários UTC, contagens não negativas, soma dos grupos
igual aos totais, `report_sha256` recalculado) antes de publicar o artefato
`incidents.json` + `summary.md` (português) + `SHA256SUMS`. A publicação no canal
`C3PO_ESCALATION_ISSUE` (padrão #429) segue a regra da varredura noturna abaixo; canal fechado,
trancado ou cheio deixa o agregado só no artefato, com aviso.

O job usa o ambiente `production`, o mesmo de `valuation-readonly-report.yml` e do
`security-watchdog.yml` agendado, que já rodam sem aprovação manual. As regras de proteção do
ambiente não foram lidas pela API nesta entrega: se um dia exigirem revisor, o agendamento
espera a aprovação como esses workflows.

### Varredura noturna de saúde

O mesmo workflow é a varredura noturna: roda também às 06:30 UTC (03:30 BRT, depois das fases noturnas), além das
11:30 UTC (08:30 BRT), com o mesmo transporte, o mesmo ambiente e os mesmos segredos (nenhum segredo novo). O
relatório (esquema `C3PO-OPS-INCIDENTS-REPORT-v2`) passou a trazer também as ingestões ainda `running` há mais de
30 min, só como contagem e idade da mais antiga (código da fonte e metadados, que podem listar símbolos, não saem).

Regra de publicação, substituindo a de "uma vez por dia": se houver cartão de saúde **vermelho**, incidente
**crítico** aberto ou incidente aberto há mais de 24 h, sai **um** comentário por execução no canal (padrão #429),
com o marcador `<!-- c3po-ops-readonly-report:AAAA-MM-DD:HHMM -->` (dia BRT e horário do agendamento, 0330 ou
0830; no disparo manual, a hora BRT do relatório), listando cada cartão vermelho por chave fixa
(`grupo/cartão`), os críticos, os abertos há mais de 24 h e as ingestões presas. Uma nova tentativa da mesma
execução encontra o marcador e não repete o comentário. Cartão vermelho ou incidente crítico também fazem o job
falhar, para a execução aparecer vermelha no Actions; só incidente com mais de 24 h publica sem falhar o job. Tudo
verde: nada é publicado. Os motivos detalhados de cada cartão continuam só no painel (o relatório é agregado e
público).

## Correções incluídas nesta implantação

`sharp` 0.35.0 → 0.35.4 (GHSA-rgj7-g3m4-5g8c) e Next.js 15.5.22 → 15.5.24 (GHSA-p293-qw3h-jr36, GHSA-2xp9-vwfh-vxw4). A auditoria npm do lockfile final retornou zero avisos. Isso comprova a resolução das dependências no checkout, não uma implantação já realizada nem exploração no host.
