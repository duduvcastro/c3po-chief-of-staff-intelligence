# C3PO_OFFHOST_IMAGE_BUILD_V1

## Objetivo

Remover do servidor de producao todo build de imagem Docker. O GitHub Actions
constroi as imagens testadas, envia os bytes resultantes ao Lightsail e o host
somente carrega as imagens e recria os containers.

## Evidencia que motivou a mudanca

Em 28/08/2026, a capacidade de burst do Lightsail chegou ao piso por volta de
15:00 BRT e permaneceu praticamente esgotada durante a tempestade de deploys.
Dos 87 samples com CPU aparente >= 90%, 77 (88,5%) ocorreram dentro de uma
janela de deploy ou nos 30 minutos seguintes. Nesses samples, a mediana visual
do problema nao era trabalho util: a media de `steal` foi 74,45%, enquanto CPU
nao-idle excluindo `steal` ficou em aproximadamente 21,65%.

O baseline de pregao sem deploy ainda mostrou carga propria relevante (p95 de
CPU nao-idle sem `steal` de aproximadamente 72,8% em 28/08). Portanto, esta
mudanca elimina uma causa comprovada de throttling, mas nao autoriza concluir
que a capacidade estrutural esta resolvida. A decisao de ampliar a instancia
continua condicionada a cinco sessoes limpas medidas pelas capacity windows.

Pacote factual local: `outputs/evidence/lightsail-capacity/2026-08-28`, report
sha256 `073e31e54043e20803e62b4de252daeffcfa962d1a694335734021ed80d13676`.

## Contrato de deploy

1. O job `Deploy production`, depois dos cinco portoes verdes, constroi duas
   imagens no runner do GitHub:
   - `c3po/backend:production`, compartilhada por API e workers;
   - `c3po/web:production`, com o SHA testado incorporado ao frontend.
2. As duas imagens recebem o label OCI `org.opencontainers.image.revision` e
   sao transportadas no mesmo arquivo gerado por `docker save`.
3. O servidor valida o SHA dos bytes transferidos, executa `docker load`,
   confere o label de revisao e sobe o Compose exclusivamente com `--no-build`.
4. O source archive continua sendo sincronizado porque `/legacy` e runbooks do
   host ainda dependem do checkout implantado. Isso nao autoriza build no host.
5. Antes do load, as imagens correntes de backend e web recebem tags de
   rollback. Se o health gate falhar, o deploy restaura essas tags e recria os
   containers com `--no-build`. O pipeline permanece vermelho mesmo quando o
   rollback recupera o servico.
6. O servidor nao recebe credencial de registry nesta versao. GHCR pode ser
   avaliado depois; V1 usa `docker save | ssh load` para minimizar superficie
   operacional e de segredo.

## Invariantes

- Nenhum comando remoto contem `docker build`, `buildx` ou `compose --build`.
- A imagem carregada corresponde ao mesmo commit que passou pelos portoes.
- Falha de transferencia, hash, label, load ou health gate interrompe o deploy.
- Politica A, risco, consumidores, TP, banco e dados persistentes nao mudam.
- Imagens de rollback nao sao removidas pelo prune de sucesso.

## Aceite

- Testes de contrato pinam build externo, transporte, load, `--no-build` e
  rollback.
- Primeiro deploy registra health verde e o SHA implantado.
- Por cinco sessoes, `server_usage` publica burst/steal e capacity windows sem
  build no host antes de qualquer decisao de compra de CPU.

## Assinaturas

- Codex: GO tecnico e implementacao, 28/08/2026.
- Fable: auditoria pendente.
- Dudu: decisao de merge pendente.
