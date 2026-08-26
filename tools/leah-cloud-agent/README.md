# Leah Cloud Agent

Aplicativo macOS local que sincroniza EventKit (Calendário e Lembretes) com o espaço pessoal Leah Cloud no C3PO.

## Segurança

- Não usa nem solicita a senha do iCloud.
- O macOS concede as permissões diretamente ao aplicativo.
- O pareamento usa código único de 8 caracteres com validade de 10 minutos.
- O token do dispositivo fica no Keychain do usuário.
- Cada dispositivo fica vinculado a um único e-mail autorizado no C3PO.

## Build local

```bash
./build_app.sh
open "dist/Leah Cloud Agent.app"
```

Para gerar o instalador publicado pela Leah Cloud:

```bash
./build_pkg.sh
```

O empacotamento usa uma área temporária fora de pastas gerenciadas pelo File Provider do macOS, remove atributos estendidos e verifica a assinatura do aplicativo antes de criar o `.pkg`.

O aplicativo exige macOS 14 ou posterior. Na primeira execução, gere o código na aba Leah Cloud, informe-o no aplicativo e aprove as duas solicitações do macOS.
