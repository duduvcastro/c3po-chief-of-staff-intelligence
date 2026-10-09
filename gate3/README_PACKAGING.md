# Gate R3 — somente empacotamento

Corrige a dependência externa do pacote R2: seu teste procurava `r1/sources/manifest_writer.py` fora do arquivo entregue. R3 inclui as sete fontes públicas exatas em `sources/` e muda apenas a referência BASE do teste delta para o diretório do próprio pacote. `image_path_adapter.py` continua byte exato no SHA `fbcb11dde975ee15434a14a12a3b6afa9977ba3b325695b5e826756c616b858e`.

Os arquivos de fonte/teste/resultados públicos R1/R2 em `historical/` preservam a proveniência; não são executados nem promovidos para resultado R3. Nenhum arquivo privado, pin físico, credencial, root operacional ou dado de host é incluído.

São duas verificações novas: igualdade do adapter/fontes e delta exclusivamente de path; extração de todo o arquivo num diretório isolado sem a árvore irmã R1, conferência de todos os hashes, imports locais e setup que encontra o manifest_writer local. O setup apenas monta a invocação fixture; nenhum método das 23 provas R1 ou das 11 provas R2 é repetido. Não há import da aplicação, SQL, transporte real ou execução do writer.

Para a nova prova de empacotamento, rode `python3 -B test_package_selfcontained.py` ao lado de `PACKAGE.tar.xz`. A ausência de árvore externa é deliberada. Esta verificação é independente da reconciliação do resultado Linux R2 já informado pela Fable, que permanece no seu próprio run/head e escopo.

Veredito: `PASS_NEW_SELFCONTAINED_PACKAGING_ONLY / ADAPTER_R2_BYTES_UNCHANGED / OPERATION_HOLD`. R3 não altera o programa, não cria recibos reais, autoridade, prova física ou GO e não certifica Monday entry.
