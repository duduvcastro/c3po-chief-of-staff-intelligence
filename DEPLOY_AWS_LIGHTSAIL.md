# Deploy AWS Lightsail

## 1. Copiar arquivos para a VPS

Na sua maquina local, dentro desta pasta do projeto:

```bash
scp -r Dockerfile docker-compose.yml requirements.txt .dockerignore .env.example work ubuntu@IP_DA_VPS:/opt/chief-of-staff-digital/
```

Se estiver usando o usuario padrao do Lightsail via SSH externo, normalmente ele e `ubuntu`.

## 2. Configurar variaveis

Na VPS:

```bash
cd /opt/chief-of-staff-digital
cp .env.example .env
nano .env
```

Preencha `EXCHANGE_APP_PASSWORD` com sua senha de app.

Proteja o arquivo:

```bash
chmod 600 .env
```

## 3. Build

```bash
docker compose build
```

## 4. WhatsApp Web

Primeiro login:

```bash
docker compose run --rm whatsapp-login
```

Enquanto o comando estiver rodando, copie o QR Code para o Mac:

```bash
scp -i /Users/eduardocastro/Downloads/LightsailDefaultKey-sa-east-1.pem ubuntu@IP_DA_VPS:/opt/chief-of-staff-digital/outputs/whatsapp-login.png ~/Desktop/
```

Abra o arquivo no Mac e escaneie pelo WhatsApp do celular.

Teste a captura:

```bash
docker compose run --rm whatsapp-capture
cat work/whatsapp_unread_today.json
```

## 5. Teste seguro sem enviar email e sem mover emails

```bash
docker compose run --rm morning-summary
```

## 6. Teste classificando emails, mas sem enviar email

```bash
docker compose run --rm morning-summary sh work/cloud_run.sh --no-send
```

## 7. Rodar enviando email, sem mover emails da Inbox

```bash
docker compose run --rm morning-summary sh work/cloud_run.sh
```

## 8. Agendar 7h e 13h

Na VPS:

```bash
crontab -e
```

Adicione:

```cron
0 7,13 * * * cd /opt/chief-of-staff-digital && /usr/bin/docker compose run --rm morning-summary sh work/cloud_run.sh >> /opt/chief-of-staff-digital/outputs/cron.log 2>&1
```

## Observacao sobre WhatsApp

O WhatsApp Web usa a pasta `whatsapp_session/` para manter o login. Se o WhatsApp desconectar, rode novamente `docker compose run --rm whatsapp-login`.
