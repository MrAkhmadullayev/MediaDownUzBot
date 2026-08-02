# AWS deployment

Loyiha GitHub Actions, Amazon ECR, EC2, SSM va Docker Compose orqali deploy qilishga tayyorlangan.

## AWS resurslari

1. Private ECR repository yarating.
2. Ubuntu 24.04 yoki Amazon Linux 2023 EC2 instance yarating.
3. EC2’ga Docker Engine, Compose plugin, AWS CLI va SSM Agent o‘rnating.
4. EC2 instance role’ga ECR image pull va SSM ruxsatlarini bering.
5. `/opt/mediadownuzbot` ichiga repositoryni joylang.
6. Production `.env` faylini shu katalogga serverning o‘zida yarating.
7. DNS’ni instance yoki Application Load Balancer’ga ulang va TLS’ni ALB/ACM yoki alohida reverse proxyda yakunlang.

Ushbu loyiha uchun `deploy/Caddyfile` hostdagi Caddy reverse proxy konfiguratsiyasini saqlaydi. Compose Nginx porti faqat `127.0.0.1:8080` manzilida tinglaydi; internetga faqat Caddy orqali `80/443` portlari ochiladi.

EC2 diskida `videos` va lokal Bot API kataloglari faqat vaqtinchalik media uchun ishlatiladi. 2 GB fayllar va to‘rtta parallel worker uchun kamida 100 GB SSD tavsiya qilinadi. PostgreSQL’ni katta production tizimida RDS, Redis’ni ElastiCache bilan almashtirish tavsiya qilinadi. Bunda `.env` dagi ikki connection URL o‘zgartiriladi va Compose’dagi lokal database xizmatlari alohida profile yoki override orqali olib tashlanadi.

## GitHub environment va secretlar

`production` environment yarating va quyidagi qiymatlarni qo‘shing:

| Nomi | Turi | Mazmuni |
|---|---|---|
| `AWS_ROLE_ARN` | secret | GitHub OIDC ishonchiga ega IAM role |
| `AWS_REGION` | variable | Masalan `eu-central-1` |
| `ECR_REPOSITORY` | variable | ECR repository nomi |
| `EC2_INSTANCE_ID` | variable | Deploy qilinadigan instance ID |
| `DEPLOY_PATH` | variable | `/opt/mediadownuzbot` |

OIDC role uchun minimal yo‘nalish: GitHub Actions ECR’ga push qiladi va faqat tanlangan instance uchun `ssm:SendCommand`, command statusi uchun `ssm:GetCommandInvocation` huquqiga ega bo‘ladi. Uzoq muddatli AWS access key saqlash talab qilinmaydi.

## Birinchi deploy

EC2 ichida:

```bash
cd /opt/mediadownuzbot
cp .env.example .env
mkdir -p videos
chmod 750 videos
chmod 600 .env
```

`.env` production qiymatlari, jumladan `BOT_TOKEN`, `TELEGRAM_API_ID` va `TELEGRAM_API_HASH` bilan to‘ldiriladi. API qiymatlari [my.telegram.org/apps](https://my.telegram.org/apps) sahifasidan olinadi.

Lokal Bot API’ga birinchi o‘tishda EC2 ichida botning bulut API sessiyasini bir marta yoping:

```bash
docker compose build bot
make local-api-init
```

Shundan keyin GitHub’dagi `Deploy AWS` workflow’ni qo‘lda ishga tushiring yoki `main` branchga tasdiqlangan push yuboring.

Workflow quyidagilarni bajaradi:

1. CI tekshiruvlari muvaffaqiyatli tugaganini kutadi.
2. Docker image’ni build qilib, SHA va `latest` taglari bilan ECR’ga push qiladi.
3. SSM orqali EC2’ga image pull va migratsiya buyrug‘ini yuboradi.
4. `docker compose up -d --remove-orphans` bilan xizmatlarni yangilaydi.
5. `/health/ready` endpointini tekshiradi.

Rollback uchun oldingi commit SHA tagini `APP_IMAGE` sifatida ishlatib Compose xizmatlarini qayta ko‘taring. Database migratsiyasini orqaga qaytarish faqat migration mazmuni tekshirilgandan keyin bajariladi.
