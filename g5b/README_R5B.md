# Gate R5b — relógios nativos da ponte

Candidato offline; OPERATION_HOLD. Corrige exclusivamente a injeção de clock operacional encontrada no constructor da ponte R5. R5 e seus 22 métodos fechados permanecem preservados; nenhum deles foi importado ou executado nesta revisão.

`ImageCapacityGate(..., clock=None)` conserva a assinatura, mas qualquer clock fornecido recusa `IMAGE_CLOCK_INJECTION_FORBIDDEN` antes de chamar leitores ou verificadores. Não existe `self.clock`. UTC e monotonic vêm do módulo fonte do programa. O parâmetro `now` do core não substitui o UTC real usado nos callbacks/gates. Snapshot, Scope, Task, Invocation e fases conservam a ABI.

A ponte marca entrada e confere o início/fim reais da tarefa. O prazo monotônico é o menor entre budget_seconds e a duração restante até not_after. Confere UTC/mono antes e depois do leitor, após o verifier obrigatório e após leitura/parser/hash completo. Regressão de qualquer relógio recusa. Depois da observação, a validade da visão tem prazo UTC de 5 segundos e prazo monotônico calculado a partir da validade restante; relógio de parede congelado não estende validade. O limite total inclui o tempo de callbacks e parsing.

Nove métodos NOVOS sintéticos PASS/0 falhas/0 erros. Os testes substituem explicitamente relógios do módulo SOMENTE como fixtures; esses relógios e seus snapshots não são prova REAL. Não se executou app, SQL, Docker, host, crypto, programas da época ou operações físicas. Nenhum fixture produz autoridade/receipt/GO.

O adapter R5 está byte exato neste pacote (SHA 78282c7e932f8082f7108eb5d22413c7580a4393ea9e3171f465d5b48ba35096); mudanças de journal64MiB, universo causal AFTER_CAPTURE, device, close e published_at permanecem com seus limites documentados na entrega R5. Essa fonte não foi alterada para esta correção. A ponte final SHA 58a6104e8d1efcab2199d388ffe17e602abf315304449dd1be5178f57f7c12ec.

O arquivo finite_batch.py incluído é C6R4 3ca239ec, somente dependência pública de codec e fixture local da ponte. Não inclui/recertifica o core operacional R5: o agente do core deve copiar o adapter e bridge R5b byte exatos ao seu novo pacote e provar sua própria integração sem repetir as provas fechadas.

Limites: a ponte recusa retorno tardio, porém não interrompe callback bloqueado por si; requer o watchdog externo POSIX do core. Runtime/clock físico/instalação/namespace/FDs/calendário aberto-fechado/SQL/readback coeso/autenticidade/revogações seguem callbacks/provas próprias obrigatórios. Fonte Python pinada e namespace real são pressupostos; isto não oferece sandbox contra código Python hostil que modifica módulos ou memória. Kernel containment contra descendentes que escapam de grupo requer prova Linux própria. A ponte não autoriza repetição física de capture após CAPTURE_NOT_YET_COMMITTED.

Arquivo autossuficiente: código público, 11 fontes originais pinadas, fixtures explicitamente sintéticas e somente os 9 novos métodos. A verificação de embalagem reconcilia membros/bytes/hash/AST; Linux próprio PENDING. Não é prova operacional ou GO da segunda-feira.
