# Rotina diária de segurança do C3PO

Solicitação do Dudu em 12/09/2026: verificar diariamente as vulnerabilidades,
procurar correções publicadas, corrigir quando houver uma atualização compatível
e verificar o funcionamento depois. A execução é por software no servidor e no
CI, sem chamadas a modelos de IA ou consultas periódicas ao Codex.

## Cobertura e horários

* **Ubuntu:** `apt-daily-upgrade.timer` e unattended-upgrades já instalados aplicam
  diariamente somente atualizações dos canais de segurança. Snapshot local a cada
  15 minutos; healthchecks de início, sucesso e falha. Reinicializações continuam
  explícitas e aparecem como pendência; não é correto prometer atualização de
  processos em memória quando o SO ainda pede reboot.
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
incompatibilidade, CI vermelho, reboot necessário ou freeze são pendências visíveis,
nunca convertidas em zero nem escondidas como “Atualizado”.

## Instalação e ativação

Esta mudança **não está ativa apenas por existir na branch/PR**. Após auditoria,
merge e deploy da revisão revisada:

```bash
sudo bash /opt/chief-of-staff-digital/scripts/install-security-daily.sh
```

O instalador usa arquivos versionados, verifica o timer de atualizações do Ubuntu,
instala unidades systemd e inicia observação/preparação com um hold inicial. Ele
não remove um hold existente. A credencial `github_governance_token` já configurada
na API precisa ler Dependabot e Actions e escrever dispatches/PR merges no repo;
403 ou indisponibilidade resulta em falha visível, nunca em ausência de alertas.
O workflow usa os mesmos secrets SSH pinados do scanner existente.

Antes de retirar o hold, conferir a execução inicial, o próximo horário do timer,
os recibos de CI e a compatibilidade com qualquer ensaio de revisão fixa em curso.
**O ensaio D14 aprovado sobre f107858f não foi re-pinado por esta alteração.** A
ativação da nova revisão precisa ser conciliada com esse compromisso; o instalador
não presume que a solicitação da rotina cancelou o freeze do ensaio.

```bash
sudo systemctl status c3po-security-daily.service --no-pager
sudo systemctl list-timers c3po-security-daily.timer --no-pager
sudo cat /opt/chief-of-staff-digital/runtime/security/security-automation-report.json
# Só após as conferências acima e conciliação da janela:
sudo rm /etc/c3po/security-maintenance.hold
```

Para suspender somente a promoção automática, criar o arquivo de hold. Para
desativar também consultas/dispatches, `systemctl disable --now
c3po-security-daily.timer`. Não alterar a política do Ubuntu ao fazer isso.

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
