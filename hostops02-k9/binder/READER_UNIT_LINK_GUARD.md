Candidata separada: restrição das units do leitor

A revisão 5996890736 cobre instalação inativa com expectativas ABSENT ou PRESENT com exatamente um link. O binder recusa PRESENT com dois links antes de aceitar qualquer lista de sobras, pelo código READER_UNIT_PRESENT_LINKS_NOT_ONE. A identidade do segundo link e a continuação exigiriam prova e revisão próprias. Uma lista genérica de sobras não supre essa prova. Os bytes do programa reader_units, a POLICY e as regras anteriores permanecem preservados; a mudança restringe os planos que esta candidata aceita.

Sem alteração do binder vigente, dos programas Fable ou da ACCEPTED_SEALS operacional. Revisão Fable e prova Linux integral deste novo hash pendentes. Testes são offline e não são prova de host.

Regressão completa desta candidata: Python3.9 328 PASS/13 SKIP/1 FAIL; Python3.12 330 PASS/11 SKIP/1 FAIL. Zero erros, zero falhas novas; cobertura de códigos de recusa passou nas duas versões. 69 testes focados passaram em cada versão. A única falha continua sendo o teste congelado W1 de stderr vazio no Python de sistema do macOS. Não há PASS integral nem prova Linux desta candidata.

Revisão2 da embalagem: relatórios JUnit locais serializados como XML válido depois da remoção de caminhos internos. Código e testes idênticos à primeira entrega; contagens reconferidas, sem repetir testes. A primeira entrega fica preservada e é substituída somente por este novo selo.
