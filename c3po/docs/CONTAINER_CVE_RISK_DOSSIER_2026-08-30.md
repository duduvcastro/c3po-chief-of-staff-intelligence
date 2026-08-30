# CONTAINER_CVE_RISK_DOSSIER_2026-08-30

## Status e fonte

Este documento e um insumo para decisao da mesa. Ele nao admite nem aceita
risco por conta propria.

- Fonte: artifact `c3po-production-container-vulnerabilities-33324558182`.
- Report: `C3PO_CONTAINER_VULNERABILITY_REPORT-v2`.
- Report SHA-256: `31184e4cd45179ed370e24323910d66be82adf2a9b69060040a905603da5f38f`.
- Revisao escaneada: `e168c259ccb55a9c4da2e269bf9b392e18bee249`.
- Metodo: ocorrencias somadas por imagem; um CVE pode aparecer mais de uma vez.
- Estado observado: 4 critical, 44 high, 99 medium e 102 low.
- Com correcao no canal instalado: 1 critical e 31 high.
- Sem `FixedVersion` para Debian 13/trixie: 16 ocorrencias critical/high,
  correspondentes a 13 CVEs distintos, todas no backend.
- Database e web: zero critical/high sem correcao.

`Sem FixedVersion` nao significa que o projeto de origem desconhece uma
correcao. Em 30/08/2026, o Debian Security Tracker mostra os pacotes de
Debian 13/trixie ainda vulneraveis e versoes corrigidas em releases Debian
posteriores. Migrar producao para Debian unstable apenas para antecipar esses
pacotes nao e recomendado.

## Revalidacao da imagem corrigida

O re-scan posterior a correcao da ordem do `apt` foi executado no run
`33329867016`. O merge-ref escaneado
`bb06a401ac8d78f12a7c38d8a59f16b50ee6f610` tem como pais `main`
`e168c259ccb55a9c4da2e269bf9b392e18bee249` e o head corrigido
`d1f6da9c1bb8e3f4971972e491db3f28657b5041`.

- artifact: `c3po-trivy-pull-request-bb06a401ac8d78f12a7c38d8a59f16b50ee6f610`;
- digest do artifact: `sha256:b47e1c6b75bb4d7d37c097fa0a522fef8372c37e7ff33ea5dab95353ad2243d9`;
- SHA-256 do JSON baixado:
  `2af74f1d9f3d98218791131bcad40f7fe6f3d3fd26dd6a44a72f9b1fb70c3a66`;
- self-hash do report:
  `8d95187d6da80bd72a37d7e061b653bd65cbaf9e3c379d777f305e3870ac6f29`;
- estado: `scan_status=complete`, `errors=[]`, 3 critical e 13 high,
  todos sem `FixedVersion`; zero critical/high fixavel.

O log de build prova duas transacoes separadas. O primeiro `apt-get update` e
`apt-get upgrade -y` consultou apenas `trixie`, `trixie-updates` e
`trixie-security`: atualizou somente `libssl3t64`, `openssl` e
`openssl-provider-legacy`, todos para `3.5.7-1~deb13u2` a partir de
`trixie-security`. So depois o Dockerfile habilitou `trixie-proposed-updates`
para o install das mesmas tres versoes exatas; essa segunda transacao registrou
`0 upgraded`. Nenhum `bash`, `libc6`, `libc-bin`, `libcap2` ou
`libsqlite3-0` foi absorvido de proposed-updates.

Inventario critical/high sem correcao efetivamente observado nessa imagem:

| Pacote | Versao instalada | Ocorrencias | CVEs distintos |
| --- | --- | ---: | ---: |
| `perl-base` | `5.40.1-6` | 8 | 8 |
| `ncurses-bin`, `ncurses-base`, `libtinfo6`, `libncursesw6` | `6.5+20250216-2` | 4 | 1 |
| `libsqlite3-0` | `3.46.1-7+deb13u1` | 2 | 2 |
| `libacl1` | `2.3.2-2+b1` | 1 | 1 |
| `gzip` | `1.13-1` | 1 | 1 |

Total: 16 ocorrencias, 13 CVEs distintos. Esse inventario substitui qualquer
leitura transitoria da imagem anterior, que havia absorvido
`libsqlite3-0 3.46.1-7+deb13u2` de proposed-updates.

## Superficie observada

Busca estatica no backend e em suas dependencias declaradas encontrou:

- nenhuma execucao de Perl ou import de modulos Perl;
- nenhuma chamada a `infocmp`, `setfacl`, `getfacl` ou APIs de `libacl`;
- nenhuma execucao do binario `/usr/bin/gzip`; os usos de gzip sao do modulo
  Python `gzip`;
- nenhum import de `sqlite3`; persistencia usa PostgreSQL via `psycopg`;
- nenhum endpoint de shell ou chamada `subprocess` no backend.

Os processos do backend ainda executam como UID 0 dentro do container. Isso
nao torna os caminhos abaixo alcancaveis, mas aumenta a consequencia de uma
falha que venha a ganhar um caminho de entrada. A migracao para usuario sem
privilegio deve ser tratada em obra separada, com testes dos volumes e jobs.

## Analise por CVE

| CVE | Pacote / ocorrencias | Condicao de exploracao | Exposicao no C3PO | Recomendacao proposta |
| --- | --- | --- | --- | --- |
| [CVE-2026-13221](https://security-tracker.debian.org/tracker/CVE-2026-13221) | `perl-base`, 1 critical | Compilar regex Perl com mais de 65.535 alternativas fixas pode produzir decisoes erradas. | Nao alcancavel: o backend nao executa Perl nem recebe regex para um runtime Perl. | Aceite temporario ate 06/09/2026; revisar imediatamente quando houver pacote trixie corrigido. |
| [CVE-2026-42496](https://security-tracker.debian.org/tracker/CVE-2026-42496) | `perl-base` / Archive::Tar, 1 critical | Extracao Perl de tar malicioso permite symlink para fora do diretorio. | Nao alcancavel: nenhum fluxo usa Perl Archive::Tar; uploads nao sao extraidos por esse modulo. | Aceite temporario ate 06/09/2026; manter proibida qualquer nova extracao Perl. |
| [CVE-2026-8376](https://security-tracker.debian.org/tracker/CVE-2026-8376) | `perl-base`, 1 critical | Overflow ao compilar regex controlada em builds Perl de 32 bits. | Nao aplicavel a arquitetura implantada `linux/amd64`; tambem nao ha execucao de Perl. | Aceite temporario por nao aplicabilidade; confirmar arquitetura em cada scan/deploy e revisar em 06/09/2026. |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | `perl-base` / Archive::Tar, 1 high | Tar malicioso declara tamanho enorme e esgota memoria durante leitura Perl. | Nao alcancavel: Archive::Tar nao e invocado. | Aceite temporario ate 06/09/2026; aguardar backport trixie. |
| [CVE-2026-57433](https://security-tracker.debian.org/tracker/CVE-2026-57433) | `perl-base` / Storable, 1 high | Blob Storable malicioso provoca overflow e encerra a desserializacao. | Nao alcancavel: o backend nao usa Storable nem desserializa blobs Perl. | Aceite temporario ate 06/09/2026; aguardar backport trixie. |
| [CVE-2026-57432](https://security-tracker.debian.org/tracker/CVE-2026-57432) | `perl-base`, 1 high | Template nao confiavel em `pack`/`unpack` pode causar leitura fora de limites. | Nao alcancavel: nao ha runtime Perl nem templates Perl vindos de entrada. | Aceite temporario ate 06/09/2026; aguardar backport trixie. |
| [CVE-2026-48962](https://security-tracker.debian.org/tracker/CVE-2026-48962) | `perl-base` / IO::Compress, 1 high | Glob de saida controlado pode executar codigo via `eval STRING`. | Nao alcancavel: IO::Compress/File::GlobMapper nao e usado. | Aceite temporario ate 06/09/2026; aguardar pacote corrigido no canal estavel. |
| [CVE-2026-42497](https://security-tracker.debian.org/tracker/CVE-2026-42497) | `perl-base` / Archive::Tar, 1 high | Hardlink de tar malicioso pode escapar do diretorio e alterar arquivo alvo. | Nao alcancavel: nenhum fluxo usa Perl Archive::Tar. | Aceite temporario ate 06/09/2026; manter proibida qualquer nova extracao Perl. |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | `ncurses`, 4 high (`ncurses-bin`, `ncurses-base`, `libtinfo6`, `libncursesw6`) | Entrada maliciosa no comando `infocmp` causa overflow de stack. | Nao alcancavel: `infocmp` nao e chamado; o backend nao oferece terminal interativo. | Aceite temporario das quatro ocorrencias ate 06/09/2026; aguardar backport trixie. |
| [CVE-2026-11824](https://security-tracker.debian.org/tracker/CVE-2026-11824) | `libsqlite3-0`, 1 high | Banco SQLite FTS5 malicioso pode causar overflow ao executar consulta MATCH. | Nao alcancavel: o C3PO usa PostgreSQL/psycopg, nao abre bancos SQLite nem usa FTS5. | Aceite temporario ate 06/09/2026; proibir introducao de SQLite sem nova revisao. |
| [CVE-2026-11822](https://security-tracker.debian.org/tracker/CVE-2026-11822) | `libsqlite3-0`, 1 high | Paginas FTS5 malformadas podem causar corrupcao de memoria. | Nao alcancavel pela mesma razao: nenhum banco SQLite e processado. | Aceite temporario ate 06/09/2026; aguardar backport trixie. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | `libacl1`, 1 high | Caller privilegiado usando pathname controlado pode seguir symlink e alterar ACL. | Nao alcancavel no codigo atual: nenhuma API ACL e chamada. UID 0 aumenta impacto apenas se surgir um caller. | Aceite temporario ate 06/09/2026; priorizar trilha separada de runtime sem privilegio. |
| [CVE-2026-41992](https://security-tracker.debian.org/tracker/CVE-2026-41992) | `gzip`, 1 high | Um mesmo processo `gzip -d`, alimentado por LZW e depois LZH maliciosos, pode ler fora do buffer. | Nao alcancavel: o backend usa o modulo Python `gzip`, nao o binario GNU gzip, e nao chama subprocessos. | Aceite temporario ate 06/09/2026; aguardar backport trixie. |

## Controles compensatorios e gatilhos

- O scan semanal permanece automatico, com dead-man proprio e report imutavel.
- O atestado diario mantem o incidente aberto enquanto houver critical/high.
- Qualquer uso novo de Perl, SQLite/FTS5, `infocmp`, ACL ou GNU gzip invalida a
  analise de nao-alcancabilidade e exige reavaliacao antes do merge.
- A chegada de `FixedVersion` no canal Debian 13/trixie exige rebuild por PR no
  mesmo dia operacional, sem esperar a revisao de prazo.
- A mesa deve escolher explicitamente entre aceitar o risco ate 06/09/2026 ou
  manter o estado de atencao sem aceite. Este documento recomenda aceite
  temporario somente pela ausencia de caminhos alcancaveis demonstrados.

Os CVEs do binario `gosu` da imagem PostgreSQL nao entram neste aceite. Eles
possuem versao corrigida do runtime Go e sao remediados nesta obra ao recompilar
o mesmo `gosu` 1.19, no commit oficial pinado, com Go 1.25.14 pinado. O entrypoint
e seu mecanismo de queda de privilegio permanecem os mesmos.

## Fora de escopo imediato

- Remover `perl-base` nao e recomendavel: ele e pacote Essential no Debian e a
  remocao pode quebrar o sistema base de maneiras nao cobertas pela suite.
- Uma base distroless ou sem Debian e uma trilha de longo prazo, com inventario
  de dependencias nativas, operacao sem shell e testes dos workers. Nao bloqueia
  a remediacao dos pacotes que ja possuem versao corrigida.
