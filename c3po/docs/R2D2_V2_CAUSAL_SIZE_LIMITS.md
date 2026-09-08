# Limites de tamanho da lista causal V2 — F386-1

O teto antigo de20MiB recusava contratos diários válidos antes da seleção. O parecer Fable da386 mediu28.684.960B para6.001 ações ordinárias e43.067.980B para9.010 linhas de todas as classes, além de aproximadamente0,9MB de cadastro. O produtor deve continuar emitindo linhas diárias apenas para as classes que precisam delas; os filtros de classe, ADV20, N_cut550 e cadastro máximo10.000 não mudam.

## Contrato de bytes

| Objeto | Teto | Fonte |
|---|---:|---|
| Cada input bruto (cadastro ou contrato diário) |64MiB =67.108.864B|`MAX_INPUT_BYTES = MAX_SNAPSHOT_BYTES`|
| Envelope causal completo canônico |64MiB =67.108.864B|`MAX_CAUSAL_ENVELOPE_BYTES = MAX_SNAPSHOT_BYTES`|
| Reserva para wrapper e dois recibos do emissor |16KiB =16.384B|`CAUSAL_RECEIPT_RESERVE_BYTES`|
| Compromisso canônico, já incluindo os dois base64 |64MiB−16KiB =67.092.480B|Envelope menos reserva|

O teto geral de snapshots permanece64MiB. Não foi elevado o limite de eventos ou a quantidade de instrumentos. Um input estar abaixo de64MiB não significa que ele caiba no envelope: os dois inputs brutos são preservados em base64, e o JSON também contém ranking, exclusões, lista, hashes e metadados.

Para input de `n` bytes, base64 ocupa exatamente `4 * ((n + 2) // 3)` caracteres ASCII, sem escapes adicionais no JSON. O construtor mede o JSON com os dois campos base64 vazios e soma os dois comprimentos codificados. Esse é o tamanho exato do compromisso final; não se usa estimativa por nome ou por barra. Somente depois de o tamanho caber são alocados os base64.

O limite bruto combinado fica abaixo de aproximadamente50,3MB antes dos metadados; dois inputs de64MiB não são admitidos juntos. As dimensões29–43MB observadas são compatíveis com o teto quando o cadastro e os metadados reais também cabem; o guard exato continua obrigatório.

## Ordem dos guards

1. `check_causal_input_sizes(registry_bytes, daily_bytes)` valida tipos/tamanhos brutos e rejeita uma soma base64 que já excederia o orçamento, antes de parsing ou I/O. O emissor deve chamá-lo antes de abrir sua conexão. Erros controlados: `CAUSAL_INPUT_SIZE_LIMIT` e `CAUSAL_ENVELOPE_SIZE_LIMIT`, sem conteúdo dos inputs.
2. `build_commitment` aplica esse mesmo guard e, após validar/calcular os metadados, confere o tamanho exato com campos vazios. Excesso não retorna compromisso nem chega à codificação base64. No emissor, isso deve preceder INSERT de evento/artefato e qualquer sink.
3. A reserva16KiB cobre as formas fechadas dos dois recibos atuais: IDs UUID, bindings duplicados, relógios UTC, wrapper e referência de publicação de até512 caracteres. A contraprova usa512 caracteres fora do BMP, que viram12 bytes de escapes por caractere, além da época máxima. A reserva não autoriza futuras expansões arbitrárias de schema.
4. `check_causal_envelope_size(envelope)` mede os bytes canônicos completos. Deve ser aplicado ao envelope efetivo antes da persistência no spool; a porta de leitura mantém o teto físico64MiB. `validate_commitment` já o aplica antes de decodificar inputs ou consultar o verificador de recibos. Não confiar apenas na reserva se o contrato dos recibos mudar.
5. `_decode` confere também o tamanho bruto efetivo depois do decode. A igualdade do comprimento base64 não basta:4,5 e6 bytes brutos podem ocupar o mesmo número de caracteres codificados.

Os helpers são puros, sem banco, arquivo, rede ou provedor. Aumentar o tamanho aceito não concede prontidão operacional. O código do emissor, da porta e do writer precisa usar este contrato compartilhado; nenhum chamador deve voltar a aceitar até64MiB por input e ignorar o envelope final.

## Evidência e custo

Contraprovas sintéticas locais cobrem6.001 nomes elegíveis com20 barras e payload válido acima de20MiB, JSON bruto de43.067.980B, rejeição acima de64MiB antes do parser, overflow combinado, fronteira exata de metadados/base64 antes do encoder, fronteira do envelope antes de verificação externa, arredondamento do decode e overhead dos recibos. A fixture exata43MB usa whitespace JSON válido para isolar bytes, não pretende reproduzir o universo do provedor. O caso6.001 contém as linhas/barras estruturadas, preserva os hashes brutos e seleciona550 nomes sem truncar o cadastro. Outro caso verifica os metadados de10.000 nomes.

Para o caso filtrado medido pelo auditor,28.684.960B diários +900.000B de cadastro resultam em aproximadamente39,45MB apenas de base64 por sessão. Em69 sessões são aproximadamente2,72GB, antes dos demais metadados; a estimativa operacional de≈40MB/dia e≈2,8GB por época continua adequada como ordem de grandeza. Com43MB de todas as classes, o custo cresce para aproximadamente4,05GB de base64 em69 sessões, razão adicional para o filtro no produtor.

Esses valores não incluem duplicação transitória de strings/objetos na memória, JSONB, índices, WAL, backups e cópias de retenção. O construtor evita alocar base64 quando a projeção já não cabe; isso não qualifica memória máxima, latência do PostgreSQL ou capacidade de69 sessões. Nenhuma carga grande no banco, coleta de provedor ou alteração de produção foi feita para esta correção. O ensaio de capacidade permanece condicionado aos recibos normalizados e ao índice de episódios ativos.
