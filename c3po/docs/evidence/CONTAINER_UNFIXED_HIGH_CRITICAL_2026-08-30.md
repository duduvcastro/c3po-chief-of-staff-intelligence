# Dossie de vulnerabilidades sem correcao no runtime — 2026-08-30

**Status:** 16 ocorrencias `critical`/`high`, 13 CVEs distintos, todas na imagem
backend Debian 13.6. Este documento classifica exposicao; nao suprime achados e
nao autoriza resolver o incidente.

## Evidencia canonica

- Workflow: [scan 33324558182](https://github.com/duduvcastro/c3po-chief-of-staff-intelligence/actions/runs/33324558182), concluido com sucesso.
- Revisao escaneada: `e168c259ccb55a9c4da2e269bf9b392e18bee249`.
- Artefato GitHub: `c3po-production-container-vulnerabilities-33324558182`,
  digest `sha256:09de9b152b08c9c4597b6b34e4844d9ec23a58c6b7c2b0205c48711da043a5b3`.
- JSON extraido: `sha256:933522aab2c6d05c47c3cba18a121afbf3056199888f7d58d29c1e2f73442ed8`.
- Self-hash do report v2:
  `31184e4cd45179ed370e24323910d66be82adf2a9b69060040a905603da5f38f`.
- Scanner: Trivy 0.74.0 pinado por digest; imagem backend
  `sha256:4700cdfc728060c675fbda420e249f7c86b2ccaeb7a3d8b324e1a0b513da5068`.

O report registra 3 `critical` e 13 `high` sem `FixedVersion` no backend.
Database e web nao possuem `critical`/`high` sem correcao.

## Metodo de exposicao

A classificacao abaixo cruza quatro fatos:

1. gatilho tecnico publicado pelo Debian Security Tracker;
2. arquivos e arquitetura encontrados pelo Trivy na imagem `linux/amd64`;
3. busca no codigo por invocacao dos binarios, bibliotecas ou modulos;
4. fluxo real do C3PO: persistencia por PostgreSQL/`psycopg`, sem executor de
   comandos de usuario.

O inventario da imagem contem somente `perl-base`; nao contem
`perl-modules-5.40`, `libarchive-tar-perl`, `libio-compress-perl` nem
`libstorable-perl`. O repositorio nao invoca Perl, `infocmp`, funcoes ACL ou o
binario `/usr/bin/gzip`. Os fluxos `.gz` do backend usam `gzip` da biblioteca
padrao Python. Nao ha import de `sqlite3`; o banco da aplicacao e PostgreSQL.

"Sem caminho conhecido" significa reducao factual de exposicao, nao
"corrigido" ou aceite de risco permanente.

## Registro por CVE distinto

| CVE | Severidade / ocorrencias | Gatilho | Exposicao real no C3PO | Mitigacao atual e recomendacao |
| --- | --- | --- | --- | --- |
| [CVE-2026-13221](https://security-tracker.debian.org/tracker/CVE-2026-13221) | CRITICAL / 1, `perl-base` 5.40.1-6 | Regex Perl com mais de 65.535 ramos fixos pode produzir falso positivo/negativo. | Sem caminho conhecido: o backend nao executa Perl nem deriva regex Perl de entrada. | Manter monitorado; instalar apenas a atualizacao oficial de Trixie quando publicada. Nao importar Perl de `sid`. |
| [CVE-2026-42496](https://security-tracker.debian.org/tracker/CVE-2026-42496) | CRITICAL / 1, `perl-base` 5.40.1-6 | `Archive::Tar` extrai symlink com alvo fora do diretorio. | Componente vulneravel ausente: `Archive::Tar` nao consta no inventario, e nao ha extracao via Perl. | Debian marcou a correcao de Trixie como adiada por risco de regressao. Aguardar pacote oficial; proibir introducao de extracao Perl. |
| [CVE-2026-8376](https://security-tracker.debian.org/tracker/CVE-2026-8376) | CRITICAL / 1, `perl-base` 5.40.1-6 | Overflow ao compilar regex em builds Perl de **32 bits**. | Nao aplicavel a arquitetura observada: imagem e `linux/amd64`; alem disso, Perl nao e invocado. | Manter visivel ate Debian/Trivy limpar o pacote; nao tratar a nao aplicabilidade arquitetural como correcao do binario. |
| [CVE-2026-42497](https://security-tracker.debian.org/tracker/CVE-2026-42497) | HIGH / 1, `perl-base` 5.40.1-6 | `Archive::Tar` cria hardlink para caminho controlado durante extracao. | Componente vulneravel ausente e nenhum fluxo Perl de tar. | Mesma trilha da CVE-2026-42496: aguardar Trixie e manter archive ingestion em bibliotecas Python auditadas. |
| [CVE-2026-48962](https://security-tracker.debian.org/tracker/CVE-2026-48962) | HIGH / 1, `perl-base` 5.40.1-6 | `IO::Compress::File::GlobMapper` avalia output glob controlado. | `IO::Compress` nao esta instalado e Perl nao e executado. | Nao instalar o modulo; absorver a correcao pelo pacote Debian oficial quando disponivel. |
| [CVE-2026-57432](https://security-tracker.debian.org/tracker/CVE-2026-57432) | HIGH / 1, `perl-base` 5.40.1-6 | Template nao confiavel em `pack`/`unpack` causa leitura fora de limites. | Funcao pertence ao core, mas nao existe chamada Perl no runtime C3PO. | Manter ausencia de executor Perl e atualizar via Trixie. |
| [CVE-2026-57433](https://security-tracker.debian.org/tracker/CVE-2026-57433) | HIGH / 1, `perl-base` 5.40.1-6 | Blob `Storable` criado causa overflow/panic em `thaw` ou `retrieve`. | Modulo `Storable` nao consta no inventario; nao ha desserializacao Perl. | Nao adicionar o modulo; acompanhar pacote oficial. |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | HIGH / 1, `perl-base` 5.40.1-6 | Header tar com tamanho enorme causa exaustao de memoria em `Archive::Tar`. | `Archive::Tar` ausente; nenhum tar e processado por Perl. | Debian adiou a correcao de Trixie por regressao upstream; aguardar pacote oficial e preservar limites nos fluxos Python. |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | HIGH / 4, `libncursesw6`, `libtinfo6`, `ncurses-base`, `ncurses-bin` 6.5+20250216-2 | Stack overflow no CLI `infocmp` ao analisar dados criados. | `/usr/bin/infocmp` existe, mas nao e chamado pelo app, entrypoint ou workers; containers sao nao interativos. | Nao expor shell/terminfo de usuario; aplicar o point release de Trixie quando houver. Debian classifica como problema menor de CLI. |
| [CVE-2026-11822](https://security-tracker.debian.org/tracker/CVE-2026-11822) | HIGH / 1, `libsqlite3-0` 3.46.1-7+deb13u1 | Banco SQLite FTS5 criado + consulta `MATCH` causa corrupcao de memoria. | Sem caminho conhecido: C3PO usa PostgreSQL, nao importa `sqlite3` e nao recebe arquivos SQLite. | Nao introduzir ingestao SQLite/FTS5 antes da correcao; acompanhar o point release Trixie. |
| [CVE-2026-11824](https://security-tracker.debian.org/tracker/CVE-2026-11824) | HIGH / 1, `libsqlite3-0` 3.46.1-7+deb13u1 | Metadata de pagina FTS5 criada causa heap overflow. | Mesmo limite da CVE-2026-11822: biblioteca presente por dependencia de base, sem consumidor C3PO. | Mesma recomendacao: nenhuma ingestao SQLite e atualizacao oficial assim que publicada. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | HIGH / 1, `libacl1` 2.3.2-2+b1 | Chamador privilegiado usa `acl_*_file()` em caminho com componente symlink controlado. | Sem caminho conhecido: codigo e entrypoints nao chamam ACL nem `setfacl`; nao existe path de usuario para operacao ACL. | Nao fazer backport isolado: Debian informa mudanca de ABI e correcao planejada para point release. Abrir hardening separado para usuario nao-root/capability drop do backend. |
| [CVE-2026-41992](https://security-tracker.debian.org/tracker/CVE-2026-41992) | HIGH / 1, `gzip` 1.13-1 | Uma unica invocacao `gzip -d` processa LZW criado e depois LZH criado, reutilizando estado global. | O binario existe, mas o backend usa `gzip.GzipFile` Python; `gzip` shell aparece apenas no transporte CI/host de artefatos internos, fora da imagem da aplicacao. | Nao encaminhar uploads ao binario; aguardar o pacote Trixie. Debian marca como problema menor/no-DSA. |

## Recomendacao consolidada

1. Manter o incidente aberto e a governanca vermelha enquanto qualquer uma das
   16 ocorrencias permanecer no report de producao. Nao clicar em `Resolver`.
2. Rodar o scan semanal e abrir bump/rebuild assim que Trixie publicar versao
   corrigida. O scanner, nao este dossie, determina o fechamento factual.
3. Nao remover `perl-base` a forca: e pacote Essential da familia Debian e a
   remocao altera a integridade da base. Nao misturar pacotes `sid/forky` em
   Trixie para obter um verde artificial.
4. Tratar imagem realmente minimizada/distroless e backend nao-root como obra
   separada, com teste de compatibilidade e rollback; nao como atalho desta PR.
5. Depois do merge auditado da remediacao fixavel, fazer novo scan da producao.
   O atestado supervisionado continua sendo acao do owner.
