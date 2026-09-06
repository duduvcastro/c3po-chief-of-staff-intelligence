# Emissor causal V1 — módulo isolado, OFF

Implementa construção transacional, publicação durável por callback, recibos e
recuperação da lista causal do contrato normativo `eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0`.
Não coleta provedores, inicia workers, altera a configuração do app ou provisiona
SQL/roles. O construtor exige `enabled=True` explicitamente. Nenhum código V1,
compose ou workflow é alterado. Esta entrega não é declaração de prontidão.

## Fronteira e composição

`PostgresCausalListEmitter(connection_factory, calendar, enabled=False)` recebe
conexões psycopg transacionais e o calendário oficial do coletor. O factory não
pode usar `autocommit=True`, fallback em memória, owner, superuser ou role
delegada. Não há parâmetro de relógio fornecido pelo chamador.

`build(epoch, day, registry_bytes, daily_bytes)` recebe os bytes privados exatos
dos dois contratos, até20MiB cada. O builder da #383 verifica a seleção assinada,
as20 sessões de liquidez e os hashes; a publicação não contém os símbolos ou os
bytes. Não se confunde essa verificação estrutural com auditoria independente
da cobertura dos fornecedores. Os booleans de cobertura continuam dependências
do rito das fontes, também para risco e earnings.

`publish(epoch, day, sink)` recebe um `PublicationSink`: ele deve publicar
duravelmente o resumo agregado, de modo idempotente, e devolver canal/referência.
Uma fila aceita ou resposta incerta deve lançar erro. O emissor usa um relógio
PostgreSQL posterior ao retorno para registrar quando observou a publicação.
Não aceita hora fornecida pelo sink ou derivada de mtime. `FileRelaySink` é a
implementação local privada; um publicador GitHub concreto ainda precisaria de
auditoria de envio/readback. O módulo não contém credenciais nem envia mensagens.

O retorno de `publish` é `{commitment,audit_receipt,publication_receipt}` completo,
revalidado com leitura independente dos eventos e confirmações já comprometidos.
`write_private_envelope` grava esse retorno no spool privado em
`causal_list/<epoch>/<D>.json`. Esse helper é somente uma primitiva de arquivo:
não atesta fatos de auditoria nem substitui a validação do coletor. O novo
`ConfirmedCausalReceiptVerifier` é opt-in e **não está ligado ao worker existente**.

## Construção, relógios e transações

Todas as operações da mesma epoch/sessão usam um advisory transaction lock.
O cálculo começa dentro da janela D−1. `built_at` é o relógio real do banco
observado após concluir o cálculo, antes de selar/armazenar o resultado. A seleção
é reconstruída com esse instante; se dados antes futuros alterarem a seleção,
a operação falha em vez de certificar duas versões. Outra leitura do relógio
confere o cutoff antes do INSERT. Artefato e evento BUILT são inseridos na mesma
transação. Não se retorna sucesso antes do commit.

Uma conexão nova observa o evento já comprometido e insere uma confirmação
somente por acréscimo com hash do recibo. Para BUILT, essa **observação pós-commit**
deve ocorrer antes de00:00 ET da sessão. `confirmed_at` não é a hora de commit da
própria confirmação; esta pode terminar depois. É a prova de que o build anterior
já estava visível naquele instante. Não se infere durabilidade de um relógio
gravado antes do commit, de um arquivo antigo ou de resposta HTTP ainda pendente.

Sem confirmação anterior ao cutoff, recuperação posterior permanece bloqueada.
Com confirmação já persistida, repetir o mesmo input retorna o mesmo artefato e
UUIDs. Input diferente na mesma epoch/sessão é conflito. A recuperação revalida
bytes, seleção, calendário, manifesto e vínculos; não usa um status salvo.

Publicação ocorre sob o mesmo lock, depois da confirmação do build. O relógio
observado após o sink deve ser anterior a10:00 ET. Evento PUBLISHED e seu vínculo
ao build são comprometidos juntos. Uma confirmação posterior atesta sua leitura
durável. A validação final recompõe o compromisso e consulta eventos/confirmacões
em novas conexões. Evento de outro build, referência inválida ou UUID reutilizado
não pode ser recuperado como sucesso.

Se o sink publicou e o commit falhou, a próxima tentativa chama o sink idempotente
e observa sua disponibilidade no relógio **atual**. Depois das10:00 não inventa
uma publicação anterior: permanece N/D mesmo que o arquivo tenha mtime antigo.
Se a resposta ao commit foi perdida, a recuperação lê o registro já persistido,
sem novo evento ou publicação. O laboratório injeta perda de resposta após um
commit real; não simula falha de disco/rede física.

## SQL e limite da autoridade

DDL em `db/manual/046_r2d2_v2_causal_emission.sql`: três tabelas novas e triggers
contra UPDATE/DELETE dos registros causais, inclusive dos respectivos eventos
em `audit_events`. A subpasta é deliberada: `Database.initialize` só percorre
`db/*.sql`, sem recursão. Portanto o SQL exige aplicação explícita auditada;
o deploy deste módulo OFF não o aplica automaticamente. O emissor nunca executa
DDL, GRANT, REVOKE ou provisionamento de role.

Provisionar separadamente a identidade emissora, com SELECT/INSERT nas quatro
tabelas necessárias e nenhum UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER, inclusive
UPDATE por coluna. Sem ownership, memberships, troca de role, CREATE em banco ou
schema, TEMP, RLS, superuser, BYPASSRLS, replication ou privilégios de criar roles.
Esses fatos são verificados em cada conexão emissora, antes de lock/escrita/sink.
O SQL não altera eventos de auditoria alheios às duas ações V2.

**Limite ainda aberto:** SELECT/INSERT e triggers impedem mutar registros
existentes por essa identidade, mas INSERT direto ainda permite fabricar um
novo evento/horário fora deste emissor. O código auditado obtém clocks do banco;
isso não é uma garantia SQL contra backdating por uma credencial comprometida.
Não se declara atendido o portão de identidade incapaz de fabricar timestamps.
Antes de prontidão, é necessário auditar uma interface de emissão restrita no
banco (ou autoridade independente equivalente), vinculando bytes e tempos
atribuídos pelo servidor, sem INSERT arbitrário pelo cliente. Administrador,
restauração e mudanças de ACL/DDL também permanecem fronteiras auditadas.

## Arquivos e recuperação

Raízes absolutas preexistentes, próprias do usuário e0700. Travessia por dirfd
e `O_NOFOLLOW`; pais/arquivos simbólicos, objetos não regulares, hardlinks e
permissões abertas são recusados. Descendentes0700, arquivos0600, até64MiB.
O resumo agregado vai no relay; o envelope com inputs fica no spool separado.

Escrita temporária exclusiva, flush/fsync do arquivo, link exclusivo sem
substituição e fsync do diretório. Retentativa só aceita bytes idênticos e
reconfere inode/tamanho/modificação; nunca sobrescreve conflito. Um crash entre
link e unlink do temporário pode deixar duas referências ao inode: a recuperação
falha fechada por hardlink até tratamento auditado do temporário, preservando os
bytes. Não há reaper ou promessa de recuperação automática desse caso. Fsync
não é alegação de teste de perda elétrica. Falha após publicação não fabrica
recibo no banco nem autoriza avançar o relógio contratual.

## Validação desta entrega

- 49 testes offline de ACL/autocommit, campos/vínculos de recuperação, cutoff e
  arquivos privados, idempotência, conflitos, symlinks, hardlinks e permissões.
- PostgreSQL16.15 real:21 testes funcionais e readback/replay após reinício limpo,
  com oito chamadas concorrentes, rollback, resultado incerto de commit, role
  restrita, triggers e timestamps reais. Sink sintético local nessa prova.
  Recibo público SHA `6c583dbf04314db2a192645fedb467f734cc12abb6d123ab8b84d5215b98a151`;
  índice17 artefatos `4118f204cecae028f29f4ab18785844aae4f68c7e82816b1dcc3b05ce2d4275c`.
  Os bytes SQL testados são os mesmos; após a prova, o arquivo foi movido para
  `db/manual/`, conservando SHA `69385142867c75dd4641a63d8a6d6e6400c73bf7ef7555b3fd800ae1e9fd90e7`.

Capacidade da época, ACK/retencão do spool, cobertura das fontes, autoridade de
timestamps resistente a INSERT arbitrário, deploy e prontidão continuam abertos.
Não usar estes testes para declarar coleta ou operação paper liberadas.
