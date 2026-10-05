BOOT — prova de candidato em runner GitHub-hosted descartável

Uma branch proposta sobre dd4ec4bb, um único workflow por push, token contents:read, actions pinadas, sem secrets, deploy ou workflow_dispatch. A Fable executa o único push autorizado. O Codex não executa Docker, host, dispatch ou push.

Cinco unidades completas são copiadas por hash, sem arquivos retirados:
  binder                  fonte bb255, suíte437 e novosBOOT93
  bootstrap_identity      família b0a, suíte151
  core_bootstrap_identity núcleo próprio4e3
  subset_registry25       registro25 exato, prova de três famílias/núcleos
  tree_conformance        K9R248c em FakeHost genuíno, recibo inteiro PARTIAL_OBSERVED e sete recusas

UNITS.json registra os cinco pins; GROUPS.json registra os quatro passos; WORKFLOW.yml.txt deve ser byte-idêntico ao único workflow. PROOF_SHA256SUMS autentica cada script/profile/documento de proof/. Os selos são conferidos antes e depois, inclusive as entradas e cópias privadas usadas pelas provas offline.

O grupo executa:
  binder-tests               suíte integral nas duas versões, W1 aninhada, verificadores reaisK8/K12/W1
  bootstrap-tests            151 casos nas duas versões e46 casos reais Go text/template
  offline-conformance-tests  subset15 nas duas versões
  offline-conformance-tests  TREE8 nas duas versões
Todos os passos de prova são tentados para preservar diagnóstico mesmo após uma falha; isso não significa seguir um passo operacional dependente. O resultado agregado recusa quando qualquer passo recusa.

Os venvs são novos e separados. As entradas autenticadas de subset/TREE são copiadas para scratch novo0700/0600; a origem staged não é chmod nem alterada. O helper executado é o mesmo buffer pinado. Resultados JSON/JUnit consumidos são preservados nos artefatos de out/, com seus hashes; stdout/stderr/status originais e resultados parciais também são conservados. Todos os inventários são exatos. Cada omissão é declarada; omissão de caso novo ou obrigatório recusa.

O artifact do grupo contém RESULT.json, RUNNER.txt, logs e JUnit de binder/W1, BOOT/Go e subset/TREE, e SEALS.after.json. O Python do sistema observado é distinto dos dois venvs exteriores. Nada antecipa as contagens futuras como PASS.

Limites: TREE tem modelo/contexto/BOUND sintéticos; subset cobre três famílias sob registro25, sem full25 sealed-copy; Go prova a linha literal do template; BOOT testa seu modelo. Nenhum destes prova consumo real da release/raw/microestrutura, systemd, kernel, Docker ou espaço do host, POLICY/boot, gates, assinatura, autoridade ou GO. O runtime físico Mac é outra candidata e não é publicado nesta árvore.
