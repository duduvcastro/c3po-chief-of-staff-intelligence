# EC Ops watchOS — runbook privado

## Pré-requisitos

1. Conta Apple Developer aprovada e Xcode completo instalado no Mac.
2. APNs Auth Key criada no portal Apple. O arquivo `.p8` é baixado uma única
   vez e deve ser salvo no Keychain/armazenamento seguro, nunca no repo.
3. Quatro secrets no environment `production` do GitHub:
   `C3PO_WATCH_APNS_PRIVATE_KEY`, `C3PO_WATCH_APNS_KEY_ID`,
   `C3PO_WATCH_APNS_TEAM_ID` e `C3PO_WATCH_APNS_BUNDLE_ID`.

## Gerar e assinar

1. Instalar XcodeGen: `brew install xcodegen`.
2. Em `c3po/watch`, executar `xcodegen generate`.
3. Abrir `ECOps.xcodeproj`, selecionar a conta Apple aprovada e habilitar
   Push Notifications e App Groups para os dois targets.
4. Confirmar o bundle id configurado no secret e no target do app.
5. Conectar o Watch ao Xcode e executar o target `ECOps`.

## Ativar o aparelho

1. No painel autenticado, emitir uma credencial owner-only por
   `POST /api/v1/watch/device-tokens`; o valor aparece uma vez.
2. No Watch, informar a URL HTTPS de produção e a credencial dedicada.
3. Selecionar as categorias e tocar em `Activate alerts`.
4. Revogar aparelho perdido por `DELETE /api/v1/watch/devices/{id}`.

## Aceite

Desligar completamente o iPhone, manter o Watch em Wi-Fi/LTE e disparar o
teste owner. Registrar chegada, toque e complication. Depois repetir com uma
chave APNs inválida e provar que jobs e Web Push permanecem saudáveis.
