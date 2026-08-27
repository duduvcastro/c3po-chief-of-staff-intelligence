# MICROSTRUCTURE_TAPE_PROBE_V1 — EMENDA 1: fonte Massive, não Databento

**Data:** 27/08/2026 · **Spec emendada:** `MICROSTRUCTURE_TAPE_PROBE_V1.md`
(sha256 `b97354c5a4889effefff2d39caae73a8a8a579e56ffc57b33c4353aab43ce3e9`).

## 1. Motivação (erratum do Fable, registrado)

A spec afirmava que o Databento fornece sale condition codes para US equities. **A afirmação era
factualmente errada** — o próprio guia de equities do provedor declara a ausência e o recurso
consta no roadmap oficial. Erro do autor da spec (Fable), detectado pelo fail-closed do Codex
antes de qualquer conta, pagamento ou custo. Nenhuma conta Databento foi ou será criada.

## 2. Substituições expressas

Esta emenda supersede EXCLUSIVAMENTE a cláusula de fonte (§2, bullet "Fonte") e o §3
(orçamento e credenciais) da spec. Passa a valer:

1. **Fonte:** endpoint histórico de trades da **Massive** — já integrada ao C3PO — que entrega
   `conditions`, preço, exchange, `participant_timestamp` e `sip_timestamp`. Propriedade
   decisiva: a Massive é o tape subjacente das PRÓPRIAS barras de minuto usadas pelos gates —
   o probe explica, com consistência interna, por que um negócio entrou ou não no OHLC oficial.
   A leitura de `no_tape_support` passa a significar, com precisão: "o tick persistido não tem
   suporte no tape que construiu as barras";
2. **Credencial:** a credencial Massive já existente no servidor, **condicionada à confirmação
   read-only do entitlement em produção** antes da primeira janela (uma chamada de prova,
   registrada no report);
3. **Custo:** incremental esperado **US$ 0**; nenhuma assinatura nova. O teto financeiro de
   US$ 50 é substituído por um **teto lógico: máximo de 300 janelas requisitadas**; acima disso
   o probe aborta e reporta parcial como parcial;
4. **Tudo o mais permanece**: categorias pré-registradas, definição determinística da amostra,
   leitura por proporções, evidência bruta + report hasheados no relay, auditoria do Fable antes
   de rodar, e a regra de que NENHUMA mudança de gate/spec decorre do resultado — consequência é
   emenda separada assinada. Os timestamps `participant`/`sip` são capturados na evidência bruta
   para uso futuro (workstream provider_ts), sem criar novas categorias nesta fase.

## Assinaturas

- **Fable:** ASSINADO — 27/08/2026 (autor da spec e do erro que esta emenda corrige).
- **Dudu:** pendente.
- **Codex:** pendente (GO técnico condicionado a esta emenda, conforme sua mensagem de 27/08).
