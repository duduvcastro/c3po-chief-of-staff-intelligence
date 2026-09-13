# Reinicialização automática após atualizações

A manutenção do SO tem autorização permanente do dono. Uma falha ao solicitar
scans no GitHub continua visível e impede promoção de código, mas não descarta
as evidências independentes, recentes e válidas necessárias ao reboot.

O reboot pode ocorrer nos fins de semana e fora da sessão de mercado nos dias
úteis (13:00–21:30 UTC protegidos). Holds explícitos, releases CERTIFIED e raízes
de ensaio atuais/futuras continuam impedindo manutenção. A agenda de merge
permanece separada. A política `automatic_reboot` controla só a reinicialização.

Antes de reiniciar, o controlador:

1. Confere saúde, evidências, pipelines, apt/dpkg, transações e ingestões atuais.
2. Segura o lock de deploy e fecha a admissão compartilhada. Consulta se todos os
   leases terminaram; se houver trabalho, adia sem interrompê-lo.
3. Confere a cobertura de todos os contêineres conhecidos, os mounts, a revisão
   dos backends e o hash do módulo carregado pelo webhook. Serviço desconhecido,
   build antigo ou processador opcional de microestrutura ativo vetam o reboot.
   O processador só está ativo quando captura bruta e processamento estão ligados.
4. Suspende apenas o PID do agendador cron e os timers ativos. Os processos filhos
   e serviços que já começaram continuam executando. Qualquer trabalho restante
   faz a tentativa devolver os agendadores ao estado anterior e adiar.
5. Reconfere o banco e as exclusões, grava os recibos e um marcador vinculado ao
   boot atual antes de solicitar `systemctl reboot`. Os marcadores são publicados
   por substituição atômica após sincronização do arquivo. O marcador impede novas
   admissões mesmo depois de o comando retornar. A reconciliação do boot seguinte
   remove os marcadores antigos.
6. O watchdog restaura os agendadores e comprova novo boot, saúde e ausência de
   `reboot-required`. Comando recusado ou reboot não ocorrido em 15 minutos
   reabre a admissão e restaura a programação. Não há loop de reboot: uma
   solicitação por 24 horas.

Se o controlador for interrompido após suspender a programação e antes de registrar
o pedido de reboot, o watchdog também restaura o recibo pendente dos agendadores.
Essa recuperação usa o mesmo lock de deploy, para não desfazer a pausa de um
controlador vivo, e preserva uma solicitação de reboot ainda em andamento.

Os leases cobrem inicialização, ciclos dos workers, requisições ASGI incluindo
background tasks, futures que ultrapassam o timeout e a fila do spool até seu
flush. HTTP novo recebe 503 durante o fechamento. Os arquivos de lock são
estáveis, criados pelo instalador antes do compose, e montados somente-leitura
nos consumidores. A rotina do servidor não utiliza modelos de IA.
O spool consulta admissão em cada mensagem, mas retém um único descritor para o
conjunto enfileirado ou ainda não descarregado. Ele só libera esse lease depois
do flush e da fila vazia, sob a mesma trava usada no enqueue.

## Instalação inicial deste protocolo

O pipeline inicializa os locks antes de subir os backends e instala os módulos
nativos após verificar a aplicação. O webhook legado precisa ser recriado com
seu compose atualizado, preservando sua imagem e credenciais. Até sua resposta
`/health` comprovar os hashes carregados, o controlador recusa reiniciar.
Uma implantação futura que altere o handler ou o módulo compartilhado também
exige recarregar esse processo; conferir apenas o arquivo em disco não basta.

O HTTP 403 de dispatch só deixa de existir após corrigir a permissão de Actions
da credencial apropriada. Esta correção não amplia permissões nem copia tokens,
e não declara a rotina inteira saudável enquanto esse erro persistir.
