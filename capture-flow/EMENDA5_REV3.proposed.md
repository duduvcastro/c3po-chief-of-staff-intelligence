# A2 — Emenda 5 rev3: captura de quinta 08/10 em um único job

MINUTA CONCRETA PARA A FABLE E O DONO, 07/10. Não é assinatura, GO ou prontidão. Substitui o rascunho E5rev2 f9eb8c204b4061dfbc028ed52e91c74b8a103cc04deee472750c9abb49a0f821 somente depois de conferência e assinatura exatas. A2 e Emendas1–4, incluindo E4rev3 1099dbb5e443b8b36eca5be5f6d616fe2e60988e021023de73b23435908789e2, permanecem nos respectivos escopos.

## 1. Autoridade excepcional que esta assinatura concederia

Somente sessão 08/10/2026: um job GitHub Actions, tentativa1, ramo ops/capture-thursday-single-job-20261008, push único pela Fable em torno de08:45BRT. Sem segunda tentativa, outro job, outra data, fallback Mac ou host alternativo. Término obrigatório antes11:45BRT. Atraso, ausência de prova, revogação, parcial ou transporte incerto recusa a sequência; nenhuma janela é ampliada.

Workflow operacional SHA256 3413dc4d76fcca5e65e092ed57b6c2b644cf0bc58be1c3ef4fbcdb3b8332012f. Layout executável SHA256 b106708d7e72d3c6b529021a1a35fa85d1076a52eb01883cd7b28597334eeac0. Manifesto das fontes SHA256 ea8ae50a9d61e12f493d24bc82f412904f8c1eee2c67655812a3c064f9224dc7. Base Linux9f5fc99c44fa0e605398f6e6f93ad1ac1d7d3dddfbeab0f11e2dfd1fbc2e3a19 no commit199b2464b009bf52473b7cf2add8ba1c7f02d3bd, mais a cópia selada das sete famílias e a sobreposição descrita no manifesto. Binder da captura9dbff222a3f815573d0cf89686f16a841260831400da40c5055999d7c71af133, registry78eb4ab25db448d677b5c54bb2f91346c194427fee88028260d1ba2f7be50d72, medidor/guardião runtime796ec07043f628b96bfdab20e5103567a70cc62c15f3ee63ce74ea36f6a0e2d6. Esses pins não são aceite da futura VM.

Bootstrap local expressamente limitado: instalar as dependências isoladas especificadas, copiar os quatro segredos de deploy já existentes para arquivos locais privados, criar uma chave age efêmera, trocar somente ciphertext e metadados pela #429/Git blobs/artifacts, conferir os148dados privados e medir a identidade do próprio job. Nenhum SSH, prepare, sign ou despacho antes do aceite externo desse runtime. Nada publica chave, token, inventário, pergunta ou saída privada legível. HTTPS/GitHub e age locais são transporte de dados, não autoridade operacional.

No host: somente o comando remoto literal `sudo -n /usr/bin/python3 -I -B -`, SHA256 dos bytes UTF-8 sem newline 76821da33cb2d2e8196c0e59fbe25e93ac7d048a4b523bfafaeec4572abff996. Alvo, chaves, known_hosts e argv completo têm pins próprios depois da medição e dos PRE do job; este hash literal não finge conhecer o argv futuro. SSH conserva StrictHostKeyChecking/IdentitiesOnly/BatchMode/ConnectionAttempts1, sem agente, forwarding, proxy ou retry. O acesso ordinário do SSH a essas credenciais locais e a autenticação/auditoria sudo estão incluídos; isso não concede acesso a arquivos da aplicação, BOOT, raiz de fontes ou SQL pela sonda.

Sonda própria08:52–09:02, último início09:00:40, só eco autenticado da identidade do job/nonce/pins, sem arquivos do host/BOOT/SQL/Docker. Primeiro Assino próprio até08:52. Depois da sonda real KNOWN_COMPLETE e recibo METADATA_ONLY_REQUIRES_REVIEW, quatro PRE próprios, quatro perguntas e quatro Assino próprios até09:30: policy_read09:26–09:34; capture_launch10:50–10:59; capture_result11:26–11:35; capture_cleanup11:29–11:34. São duas leituras e duas escritas, conforme as famílias seladas; nenhum outro efeito ou escrita é concedido.

As cinco respostas vêm do dono via AskUserQuestion pela Fable, uma por folha e pergunta exata. Fable registra pela própria conta autenticada na #429, com folha/pergunta/job/nonce/tentativa e horário. É registro pela Fable, não assinatura criptográfica independente. O job reconsulta pergunta e resposta, compara bytes e recusa edição, duplicidade, outro job e resposta fora do prazo. REQUEST/BOUND assinados não mudam depoisAssino.

A identidade física Linux do próprio job08/10 será medida depois do bootstrap: executável/stdlib/venv/dependências/SSH/processo/cache/fontes/contexto/nonce/autoridade e instante real. Exige parecer externo pelos bytes desse recibo, não PASS histórico nem hash futuro inserido neste documento. Antes08:51 a Fable precisa publicar o controle que cite o parecer real PASS_PHYSICAL_RUNTIME da #429 e o recibo/contexto próprios. Os quatro novos BOUND também exigem pareceres reais que nomeiem request/payload exatos até09:30. Se não existirem, nada operacional é enviado. A prova Linux de hoje é prova do código/casos sintéticos; não substitui a VM de amanhã.

Antes D e R de capture_launch, conferir commit_result e publish_launch reais completos na MESMA trilha P ou S, mesma gradeG19/dia08/host/BOOT, resultado/transporte e documentos rederivados. Essa cápsula separada não altera um REQUEST assinado nem acrescenta futuro recibo a ele. Policy completa é outro requisito; result/cleanup dependem do LAUNCH completo. D publica intent sem spawn, GET exato, espera120s; R revalida runtime/autoridade/bytes/portões/horário e ocorre no máximo uma vez. HALT próprio ou incerteza encerra, sem GO transferido.

## 2. Eleição exclusiva e retirada das autoridades Mac

Ao assinar estes bytes, o dono retira somente as quatro autoridades Mac identificadas abaixo. A Fable remove-as do driver/fila e publica um registro próprio da retirada antes de qualquer novo PRE do job. Originais são preservados para história, mas não são executados por ninguém. A existência de um portão externo não é prova de que todos os caminhos antigos se tornaram impossíveis: a retirada documental e o registro operacional são requisitos separados. Sem ambos não há novos PRE.

| Folha | SHA folha | SHA config Mac | SHA GO Mac |
|---|---|---|---|
| capture_cleanup | 9947af8b8dfae26d15adab3e89eaf5b2779ded1af68a7426e66da0886d19298c | 38f90d6ed8f79855a0de12cff42927290c953b3be76fa278489d09fc5d179e64 | 0143a4eb96618aff71c5d97fb7595369c2df49b9478c9a9589f41c218a8403dd |
| capture_launch | d18fa79b8180d03eeb78245f80bb7a4235fadcb17800ecf76c21a3c64f6181d5 | 3995f8a6483c702ec142d9da5f44acfb5b45a35346ad51effa73cca1f114bd40 | a24425ba3faf7454dce0c5e472c2db61ec194dbd784d443190d76091eaaf7b12 |
| capture_result | e0c70fabf828ae95bcdc932943a3e5067a594fb2665152ec632cb4cf0ea52621 | 9e2a55ca3aa8a9d99a6d602e5ec6a240546e5a31d660d3ee91ce2b3fbfdd2254 | 79517c124f10e33e6ec84f58c85ca68d998ba723bc3963eb32a5b2940c5eb6b5 |
| policy_read | 3cbba6513c8a5910cc0cc08b804e05cff0cbd79b3eb8b501f5ff4b27b48e5d28 | 00485fcc66681afc6b1ed8f3da62ff69f13103dbb9d03bad77671576cb605a22 | 20fc20045746494a99359b6636fbc1266fca5ce51a64312b99db6217bb661dcb |

## 3. Cifra, limites e validade

Inventário privado fixo8671e15a46627734dbcc133d59b42b574ffea134548d0cec408bec2177bb5e69,148arquivos. Entradas cifradas para a chave pública efêmera do próprio job; chave privada nunca exportada. Saídas exclusivamente para age1knekenhrh79x9xm0ghvhltwg075d33mljhu4y6u9zyz3cweszens2vr8x0. age1.3.2 Linux, binárioeb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c e keygen0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899; cifra não autentica decisão.

Validade da assinatura até08/10 às12:00BRT, operação só antes11:45. Revogo a A2 revoga esta emenda; Revogo a emenda5 revoga só esta. Fable registra HALT próprio imediatamente; job confere antes de etapas/D/R e durante esperas. Nada depende do dono após22:00; sem Assino22–07. Nenhuma promessa de duração, capacidade, provedor ou entradas na quinta.

Resposta humana proposta para estes bytes: Assino a emenda5 rev3 da A2.
