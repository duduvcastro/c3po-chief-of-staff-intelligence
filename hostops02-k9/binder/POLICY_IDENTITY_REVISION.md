Candidata separada: revisão de identidade POLICY

ID do worker e hash do boot devem ser copiados por $from do mesmo recibo K9R POLICY completo. Findings vazio, worker em execução na imagem assinada e boot igual à evidência são obrigatórios. POLICY termina antes da janela dependente; para K3-K9, TREE termina antes do POLICY. ID digitado, recibos separados, ponte por uptime, campos ausentes, relógio sem UTC, leitura parcial ou ordem invertida são recusados. A regra vale para K3-K9 e K3 secret.env.

K9R rev 5 revisado: operação 248c2ae45d096ec3dfa8a845ecff8d1032f8d02bb71ec6cdfc019d70c7710c66; prova Linux 37321530766, RESULT 0138a60218ab57f38b05d820eeb5f0bc6df9cf7c2c44eebdbad54e3f3fc02127. Esta referência não integra o selo à lista operacional.

Regressão local: py3.9 296 PASS/13 SKIP/1 FAIL; py3.12 298 PASS/11 SKIP/1 FAIL. A única falha é a já conhecida do payload W1 congelado no Python de sistema do macOS. Testes focados: 32 PASS em cada versão; a ordem TREE/POLICY tem mais três negativos cobertos na regressão integral. Cobertura de códigos de recusa passou. Sem PASS integral, sem prova Linux deste binder, sem prova de host ou GO. Revisão independente da Fable e prova Linux pendentes.

A dependência externa por hash de config.py e as adaptações privadas dos fixtures permanecem conforme PORTABILITY_REVISION.md. Binder vigente e ACCEPTED_SEALS operacional intocados. Casos unitários POLICY são sintéticos; não afirmam que o host já produziu o recibo exigido.
