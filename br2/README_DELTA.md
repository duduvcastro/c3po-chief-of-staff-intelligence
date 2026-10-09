# Executor R2 — guardas primitivas e grupo do limite externo

Nova cópia sobre R1 fonte `089523de71b6ffa056b5eda3f16296df21d350baad381bc1650418549c1020d6`. O R1 permanece imutável. As 22 provas R1 não são repetidas nem atribuídas a esta revisão.

Corrige as últimas comparações anteriores ao worker: operation precisa ser string antes da unicidade/hash; argv precisa conter somente strings antes da comparação de prefixo; SHA de fonte/stdin precisa ser pin válido antes de igualdade. As entradas do serviço precisam ter a forma dataclass congelada exata do Invocation do core, sem descritores/callbacks de lookup e com prazos UTC/monotônico primitivos. Não se aceitam objetos externos arbitrários.

`Registry(..., containment='OWN_SESSION')` mantém a sessão interna própria. `containment='INHERITED_OUTER_GROUP'` é uma opção explícita incluída no SHA do registry, destinada somente ao novo limite externo de UMA operação do core L12. Nesse modo o chamador deve ser o líder físico real da sessão/grupo; o worker confere que seu pai é esse líder, conserva o grupo e revalida grupo/sessão após os callbacks. O inner não chama setsid nem envia killpg contra o grupo do outer. Seu watchdog e sua limpeza encerram/recolhem somente o worker interno.

O outer passa a assumir obrigatoriamente: killpg de todo o grupo, recolhimento de seu worker, relógio/limpeza antes da gravação terminal durável e antes de qualquer próxima operação. Os filhos do transporte e descendentes que mantêm o grupo pertencem ao outer. O inner sozinho não certifica o encerramento de todos esses descendentes no modo herdado; um recibo retornado por ele ainda depende da limpeza final do outer. Escape deliberado de sessão/grupo e a contenção Linux real continuam exigindo prova independente.

O verificador real de runtime/current pins precisa reconciliar a topologia efetiva e o modo registrado. Não há registro operacional padrão, prova de processo físico, recibo/autoridade/GO emitidos por este pacote, ou ABI Docker inventada. Os modos `FD_EXEC_LINUX` e `NAMED_EXEC_POSIX` do executável continuam explícitos, sem fallback. Named exige imutabilidade física dos caminhos; Linux FD exige prova Linux própria.

Sete testes novos delta passaram: três campos hostis recusados antes de hash/igualdade; Invocation/clock opacos recusados; inherited sem líder físico recusado; alteração do modo muda o pin; processo fixture outer com sessão própria executa inner preservando seu grupo, e o teste encerra/recolhe o outer. Nenhum método R1 foi importado ou repetido. Testes não executam app, host, SQL, Docker ou SSH.

API do construtor BoundedRunner e `service(Receipt)` mantém os nomes R1; a configuração do grupo está exclusivamente no Registry. Veredito `PASS_NEW_PRIMITIVE_AND_INHERITED_GROUP_DELTA_ONLY / OUTER_INTEGRATION_AND_LINUX_PENDING / OPERATION_HOLD`.
