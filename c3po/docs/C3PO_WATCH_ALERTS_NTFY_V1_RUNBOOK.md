# C3PO Watch Alerts ntfy V1 — Runbook

## Segredos e acesso

O ambiente `production` do GitHub deve conter quatro segredos:

- `C3PO_NTFY_AUTH_USERS`: hashes bcrypt e role `user` dos usuários `c3po-publisher` e
  `dudu-devices`; o hash de `dudu-devices` deve ser gerado a partir do próprio token read-only,
  pois o app iOS envia credenciais por Basic Auth;
- `C3PO_NTFY_TOPIC`: tópico aleatório com pelo menos 16 caracteres;
- `C3PO_NTFY_PUBLISH_TOKEN`: token do usuário com ACL `write-only`;
- `C3PO_NTFY_SUBSCRIBE_TOKEN`: token distinto do usuário com ACL `read-only`.

O pipeline grava apenas base URL, tópico e token de publicação no `.env` principal. O token de
leitura existe somente em `c3po/ntfy.env`, modo 600, visível ao contêiner ntfy. Nenhum valor deve
ser exibido em log, issue, PR ou chat.

## Provisionamento

1. Criar `ntfy.eduardocastro.com.br` na zona Cloudflare apontando para o mesmo host/proxy do C3PO.
2. Gerar dois tokens ntfy distintos. Gerar o hash de `dudu-devices` usando o token de leitura
   como senha e um hash separado para `c3po-publisher`. Formatar `C3PO_NTFY_AUTH_USERS` como
   `c3po-publisher:<hash>:user,dudu-devices:<hash-do-token-de-leitura>:user`.
3. Gravar os quatro segredos no environment `production`.
4. Rodar o pipeline pelos cinco portões. Ele puxa a imagem oficial pinada, valida/recarrega o
   Caddy e exige o contêiner saudável no health gate.
5. Confirmar que um POST sem autenticação recebe HTTP 401/403 e que o system-health exibe
   `ntfy Watch Alerts` como operacional.

Atualização da imagem é manual-only: novo digest entra por PR, testes e auditoria. Não instalar
watchtower nem qualquer atualizador automático.

## iPhone e Apple Watch

1. Instalar o app oficial **ntfy** no iPhone.
2. Adicionar o servidor `https://ntfy.eduardocastro.com.br`.
3. Em **Settings → Users**, adicionar `dudu-devices`; no campo de senha, informar o token
   read-only. O app iOS o envia por Basic Auth, e a ACL do usuário limita a credencial a leitura.
4. Assinar o tópico secreto configurado em produção.
5. No iPhone, habilitar notificações para ntfy.
6. No app Watch do iPhone, abrir **Notificações** e habilitar o espelhamento de ntfy.

## Aceite supervisionado

1. Bloquear o iPhone e usar a rota owner de teste do C3PO.
2. Confirmar vibração e notificação no Apple Watch; preservar screenshot como atestação.
3. Parar somente o contêiner ntfy e repetir o teste: web push deve chegar e o emissor deve
   retornar sem afetar o chamador.
4. Reativar o contêiner e confirmar recuperação do card no tick seguinte.
5. Testar publicação sem token e confirmar recusa.
