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
  `dependency-security.yml`. A credencial permanece no host; a exportação contém
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
com `sudo bash scripts/install-security-daily.sh`. A primeira instalação ativa a
política autorizada, incluindo automatic_reboot. Atualizações preservam configurações
locais e todo hold explícito. A credencial já configurada na API precisa ler
Dependabot/Actions e escrever dispatches/merges; falhas nunca significam zero avisos.
Não há credencial de provedor no controlador nem chamada de mercado.

Para manutenção especial, criar `/etc/c3po/security-maintenance.hold`: suspende
promoções, reboot e recuperação de timers. Consultas continuam. Para pausar toda
a rotina, criar o hold antes de desabilitar os dois timers. Nunca reativar timers
datados de ensaios anteriores. A revisão D14 precisa ser reconciliada com Fable
após esta implantação; esta rotina não concede execução de ensaio/captura.

## Evidência e falhas

`runtime/security/security-automation-report.json` é escrito atomicamente, com
SHA-256 e horário UTC. Preserva pendências, reboot, hashes dos scans, revisão
implantada, dia do último dispatch e o resultado da promoção. Erro de leitura,
credencial, parser ou consulta não produz um relatório saudável. Relatório ausente
ou antigo aparece no painel; falhas geram notificação de job pelo mecanismo existente,
deduplicada por dia. A disponibilidade do worker de governança continua coberta
pelo seu healthcheck externo existente.

Validação de aceitação em produção: timer habilitado, primeiro ciclo registrado,
permissões do token conferidas, PR/CI/merge controlado na janela e scan posterior
mostrando os avisos resolvidos. Não executar esse ensaio durante o D14.

## Correções incluídas nesta implantação

`sharp` 0.35.0 → 0.35.4 (GHSA-rgj7-g3m4-5g8c) e Next.js 15.5.22 → 15.5.24 (GHSA-p293-qw3h-jr36, GHSA-2xp9-vwfh-vxw4). A auditoria npm do lockfile final retornou zero avisos. Isso comprova a resolução das dependências no checkout, não uma implantação já realizada nem exploração no host.
