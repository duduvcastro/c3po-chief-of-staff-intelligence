Novo contrato de transporte limitado para os gates C6. Ele permite conferir a
capacidade diária antes da captura e a cópia/universo causal depois da captura
sem enviar o diário inteiro ao gate. A imagem, o histórico e os programas
operacionais da Fable não são modificados. Este pacote não contém autoridade,
aprovação REAL, verificador físico aprovado ou conexão PostgreSQL.

O replay publicado pela Fable usou o adapter R2 `fbcb11dd…`, com teto 16 MiB.
O R5b `78282c7e…` já usa 64 MiB por buffer, mas ainda transporta e verifica todos
os registros. A fonte nativa atual `r2d2_v2_store.py` `9f9887c2…` confirma que
`read_with_journal` lê uma transação REPEATABLE READ READ ONLY e verifica a cadeia
retida inteira. Uma seleção de hashes não prova inclusão ou ausência nessa
cadeia linear. A presente mudança é um ABI novo, não truncamento do ABI antigo.

`bounded_readback.build_readback` é um produtor puro. Recebe row/records integrais
e verifica as definições puras exatas da fonte nativa por AST, sem importar o
aplicativo, acessar o DB ou executar o worker. Antes dessa verificação aplica
os tetos 8 MiB para o estado canônico, 2 MiB por registro, 128 MiB de diário e
1.000.000 registros. A memória e o tempo da obtenção dos objetos integrais já
residentes continuam sendo deveres do produtor REAL e de seu limite externo.
O produtor não converte leituras parciais, corruptas ou uma cadeia só de sufixo
em prova. Ele não compacta, apaga, reescreve ou cria um novo início do diário.

O argumento obrigatório `state_pg_text_bytes` é a medição original
`octet_length(state::text)` do PostgreSQL, extraída NA MESMA transação e snapshot
da row. Seu valor precisa ser positivo e até 8.388.608. O retorno nativo atual
de cinco colunas NÃO fornece essa medição; a adaptação REAL precisa acrescentá-la
à SELECT da row dentro da transação READ ONLY que também lê o diário. Uma segunda
conexão/consulta posterior não prova atomicidade. O teto adicional do JSON
canônico Python é conservador: os dois tamanhos não são semanticamente iguais.
O verificador REAL confere ambos e seus originais. A projeção não eleva nem
contorna o limite `LIVE_STATE_TOO_LARGE` do `read_live_inventory` nativo. Estado
original acima do teto continua recusado mesmo que os campos projetados caibam.

O output tem no máximo 4 MiB, com epoch/day/scope/fase/REQUEST/BOUND e source pins;
estado projetado em daily_capacity[D] e cinco campos concretos de sessions[D];
originais capacity-prepared:D e universe:D, ou ausência explícita; state_sha,
manifest_sha, version, head, count, hash e tamanho dos originais integrais;
tamanhos originais do estado; e bytes/hash de uma declaração de origem própria.
O hash do estado original permanece o original. A projeção tem um hash separado
e não declara ser o estado integral. As duas sessões/dias não se misturam.
O produtor recebe a declaração de origem como bytes: gerá-la e provar seus fatos
é dever do fornecedor aprovado, não deste codec. Nenhum campo booleano é prova.

API do produtor, sem efeitos:

```python
readback_raw = build_readback(
    row, records, scope=scope, phase=phase, mode="REAL",
    observed_at=actual_snapshot_observed_at,
    request_sha256=actual_request_sha256, bound_sha256=actual_bound_sha256,
    origin_statement_raw=actual_origin_original,
    state_pg_text_bytes=actual_same_snapshot_pg_size,
)
```

`observed_at` é o horário original de aquisição/estabelecimento do snapshot;
nunca o horário posterior em que a verificação terminou. Deslocar essa data
para mascarar uma leitura demorada seria recusado pelo verificador REAL. O gate
exige idade até cinco segundos, mede UTC nativo e tempo monotônico, e reconfere
janela/budget/freshness depois dos callbacks e da decodificação. O watchdog
externo R6 continua necessário para interromper callbacks que não retornam.
Este pacote não instala, inicia nem substitui esse watchdog.

`BoundedSnapshot` tem receipt_raw/readback_raw/manifest/observed_at/epoch_catalog/
journal_root/settings_journal_directory e os mesmos campos opcionais de READY,
catálogo de sessão, raiz de sessão, fechamento e pin de calendário. Não aceita
o Snapshot antigo nem `records_raw` truncado. `BoundedImageCapacityGate` mantém
a chamada `(plan, phase, now, task)` e acrescenta à construção:

```python
gate = BoundedImageCapacityGate(
    scope, approved_snapshot_read, approved_snapshot_verify,
    journal_directory=actual_journal_directory,
    readback_rule_raw=approved_rule_original,
    readback_rule_sha256=approved_rule_sha256,
    rule_verifier=approved_rule_verifier_binding,
    readback_verifier=approved_readback_verifier_binding,
    request_sha256=actual_request_sha256, bound_sha256=actual_bound_sha256,
    read_authority_raw=actual_own_read_authority_original,
)
```

A regra estática é `R2D2_IMAGE_BOUNDED_READBACK_RULE_CANDIDATE_V1`, definida de
forma estrita no decoder. Ela fixa os sources, paths, duas seleções, teto e
identidades/pins dos dois verificadores. Não há regra REAL produzida aqui.
Sua aprovação própria e seus originais SOURCE/registro/REQUEST/BOUND precisam
existir antes de uso REAL. O hash de REQUEST deve ser o hash do plan canônico;
a autoridade original de leitura deve ter o mesmo hash da autoridade finita
em Scope e plan. SOURCE/consentimento do programa não concede SQL por si.

ANTES de `snapshot_read`, o gate valida a regra, ambos os bindings REAL e chama
o verificador de aprovação com o original da autoridade de leitura, REQUEST,
BOUND, scope, fase, relógio atual, plan e task. Esse verificador deve conferir
autenticidade/assinatura, autorização específica desta leitura, janela,
revogações, origem, derivação aceita, ambiente aprovado e consumo do CLAIM R6.
Recusa ou binding inexistente/alterado impede o callback de leitura. Essa prova
é rechecável e não autoriza uma segunda tentativa física ou outro lote.

O verificador de readback é separado e obrigatório. Depois da leitura recebe
bytes imutáveis do transporte, declaração de origem e todos esses vínculos.
Ele precisa conferir a origem real do produtor/conexão/namespace, identidade
física e sources correntes, MESMA transação READ ONLY, snapshot integral e seus
state_sha/version/head/count/hashes/tamanhos, verificação integral da cadeia,
exatidão dos paths e seleção/ausências, horário original e autorização atual.
O verificador antigo `snapshot_verify` continua obrigatório para arquivos
originais/FDs/ancestrais/mounts/epoch.json/settings/manifest/READY/calendário.
Ambos retornam somente None após sucesso; True não é atestação nem fallback.

Um binding REAL exige função de módulo já carregado e pin do arquivo aprovado.
Isso é um protocolo dentro de um processo Python protegido e aprovado. Não
sandboxa um chamador Python hostil nem garante imutabilidade de `__code__`,
globals, filesystem, relógio físico ou namespace. O installer/registry/runtime
e o supervisor físico precisam provar essas fronteiras. O token privado
VerifiedBoundedJournal também é protocolo Python, não prova criptográfica ou
contenção de kernel. O decoder o cria apenas após os verificadores obrigatórios;
o adapter confere novamente hashes da projeção e dos selecionados antes de uso.

Os gates de tempo/READY/SESSION/manifest/epoch/UID0/dispositivo/autoridade/veto
anteriores permanecem. BEFORE_CAPTURE e AFTER_FIRST_CYCLE exigem daily_capacity
e conferem uma cópia se já existir, sem exigir uma cópia futura em caso B.
AFTER_CAPTURE exige cópia exata e universo causal original comprometido depois
de capture_open. Ausência retorna CAPTURE_NOT_YET_COMMITTED; não emite Receipt
COMPLETE nem autoriza retry/catchup físico. O resultado COMPLETE de captura,
seu decoder/proveniência e a interposição real antes da primeira SESSION são
obrigações separadas da casca. Este pacote não resolve o limite temporal do
lançamento PRE_OPEN nem cria um actor SESSION.

As provas locais novas usam somente bytes/objetos/relógios de fixtures
explicitamente SYNTHETIC. A medição PG nelas é um valor sintético, nunca uma
consulta ao PostgreSQL. A seleção grande contém mais de 20 MiB de diário e
fica abaixo de 12 KiB de transporte com anchors originais; não é benchmark
do servidor. Linux próprio, integração com leitor REAL, memória/CPU/tempo
físicos e aprovação dos dois verificadores permanecem pendentes. Nenhum teste
fechado do R2/R5b/core/J4/codec41 foi repetido por esta entrega.
