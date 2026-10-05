# Família HOSTOPS02_BOOTSTRAP_IDENTITY, revisão 1

Candidato offline da operação GO_WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_01. Não é GO, aceite de host, prova Linux ou validação L1/L2. O núcleo próprio fica ao lado em core_bootstrap_identity; a família não usa um núcleo compartilhado mutável. build/ contém quatro slots de runtime e documentos UNBOUND deliberadamente recusados.

O único efeito autorizado pelo desenho é o claim permanente da época/slot sob CLAIMS. Antes dele, o programa exige todas as observações e a estabilidade; depois, repete identidade, ambiente, boot, arquivos não secretos, metadados de setembro, capacidade, pais e ausências. Qualquer mudança após possível criação conserva o claim e produz PARTIAL/HOLD. Nunca remove, repara ou reabre o slot para retry.

A janela compilada é 06/10/2026 20:43:00–20:48:00Z e o orçamento é 60s. Data, modo, época, slot, chave e janela divergentes são recusados antes do primeiro efeito. Datas propostas/assinaturas/autorizações externas não são inferidas dos arquivos UNBOUND.

CONTRACT.txt e INTERFACE.json definem os campos para o novo binder. Bootstrap completa fornece identidade observada somente ao primeiro K3-K9. K3secret.env depende da cadeia bootstrap→K3 COMPLETE validada pelo novo binder. Um claim único impede duas execuções bootstrap, mas não garante uma única citação de recibo por pedidos K3 distintos. K9R/POLICY diários continuam sem a exceção bootstrap.

VALIDATION.json atribui cada prova aos bytes efetivos. Os positivos usam IDs, credenciais-canário e autoridade sintéticos. Os testes de exclusão/crash/timeout nativos criam somente arquivos em diretórios privados temporários ou processos Python locais seguros; não simulam root Linux como host real. Testes de syscall/fsync injetados demonstram fail-closed, não a durabilidade física de um host de produção. Go real e protocolo Linux ficam em provas complementares obrigatórias; ausência do Go local não é PASS.

A linguagem absoluta da Emenda2 rev1 sobre nenhuma leitura de valor secreto não está reivindicada: Docker CLI/daemon recebem o objeto inspect. Python recebe só cinco pares booleanos; nenhum conteúdo de credential file é aberto e nenhum valor secreto é publicado. A redação corrigida da Emenda2 rev2 declara esse alcance; prova Linux e revisão dos bytes efetivos continuam necessárias antes da promoção.
