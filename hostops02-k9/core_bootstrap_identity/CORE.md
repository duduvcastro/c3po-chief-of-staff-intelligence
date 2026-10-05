# Núcleo próprio bootstrap, revisão 1

Este diretório é uma geração independente derivada do núcleo HOSTOPS02. Não modifica os núcleos antigos nem torna o K9R diário capaz de escrever. PROVENANCE.json identifica cada origem por SHA256 e cada cópia preservada.

O payload leva somente core, runner, docker, parents e claim. O assembler fixa os oito arquivos de parts/reviewed_base em PINS; seu SHA256 é CORE_SHA256. CORE_SHA256SUMS cobre os arquivos do núcleo, inclusive assembler, documentação e testes. seal.py write é uma ação offline do construtor; check confirma bytes sem escrever. Depois de fixar PINS, reconstruir o payload e executar os testes contra esses bytes.

Delta próprio: classe WRITE_BOOTSTRAP só em 06/10; redução conserva claim/mode/boot; template LIVE rejeita qualquer duplicação dos cinco nomes, idêntica ou divergente; NativeClaim oferece apenas create/write/fsync. A família escolhe O_EXCL/O_NOFOLLOW/O_CLOEXEC e 0600. Nenhuma primitiva unlink, mkdir, rename, chmod, chown ou truncate integra o payload. Nenhum comando de criação/remoção/ativação de container existe na tabela da família.

NativeRunner e parents preservam bytes do núcleo de origem. Os testes compartilhados conformance/family/hostemu também são cópias byte-idênticas; a família seleciona apenas contratos de autenticação preservados e acrescenta seu contrato de data/slot/claim, sem mudar as assertions antigas. A suite selecionada não é apresentada como a suite integral de todas as famílias HOSTOPS02.

O runner limita argv, tempo e saída; stderr permanece DEVNULL como no núcleo herdado. Não se alega capturar stderr interno dos comandos Docker. Um erro retorna código/errno/estado disponível e bloqueia dependentes; não há nova supressão de warning na construção ou no transporte da prova.

Docker CLI/daemon processam Config.Env; o template envia somente present/equal dos cinco nomes aprovados ao Python. O núcleo não satisfaz literalmente uma proibição de qualquer processo ler qualquer valor secreto. Não abre conteúdo dos arquivos de credenciais, não publica seus valores e não acrescenta nova leitura de credenciais. A Emenda2 rev2 corrige esse alcance. Promoção ainda depende da prova Linux e da revisão dos bytes efetivos.
