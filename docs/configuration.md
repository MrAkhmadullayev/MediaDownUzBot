# Konfiguratsiya

## Majburiy qiymatlar

| O‘zgaruvchi | Mazmuni |
|---|---|
| `BOT_TOKEN` | BotFather tokeni |
| `TELEGRAM_API_ID` | `my.telegram.org/apps` saytidan olingan ilova IDsi; lokal Bot API konteyneri uchun |
| `TELEGRAM_API_HASH` | `my.telegram.org/apps` saytidan olingan maxfiy ilova kaliti |
| `ADMIN_TELEGRAM_IDS` | JSON ro‘yxat ko‘rinishidagi admin IDlar |
| `ADMIN_BASE_URL` | Bot admin havolasini yasaydigan public URL |
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL manzili |
| `ALEMBIC_DATABASE_URL` | Sync Alembic PostgreSQL manzili |
| `REDIS_URL` | Redis broker va FSM manzili |
| `FIELD_ENCRYPTION_KEY` | Fernet kaliti |

Fernet kalitini generatsiya qilish:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Limit va unumdorlik

| O‘zgaruvchi | Standart | Tavsif |
|---|---:|---|
| `TELEGRAM_API_BASE_URL` | `http://telegram-bot-api:8081` | Docker tarmog‘idagi lokal Bot API manzili |
| `TELEGRAM_LOCAL_MODE` | `true` | Aiogram lokal Bot API rejimi |
| `TELEGRAM_UPLOAD_LIMIT_MB` | `2000` | Lokal Bot API orqali ruxsat etiladigan maksimal fayl hajmi |
| `TELEGRAM_UPLOAD_TIMEOUT_SECONDS` | `3600` | Telegram’ga katta fayl yuborish timeouti |
| `MAX_DOWNLOAD_SECONDS` | `3600` | Celery task vaqt chegarasi |
| `MAX_VIDEO_HEIGHT` | `2160` | Eng yuqori video sifati |
| `WORKER_CONCURRENCY` | `4` | Bitta worker konteyneridagi parallel tasklar |
| `MEDIA_METADATA_CACHE_TTL_SECONDS` | `86400` | Media sifati va hajmi tahlili keshining amal qilish vaqti |
| `MEDIA_DEDUP_RETRY_SECONDS` | `3` | Bir xil media boshqa workerda tayyorlanayotganda qayta tekshirish oralig‘i |
| `WORKER_DNS_PRIMARY` | `1.1.1.1` | Worker uchun asosiy DNS resolver |
| `WORKER_DNS_SECONDARY` | `8.8.8.8` | Worker uchun zaxira DNS resolver |
| `LOG_LEVEL` | `INFO` | Log darajasi |

## Production qiymatlari

Production’da `APP_ENV=production`, `COOKIE_SECURE=true`, `ADMIN_BASE_URL=https://admin.example.uz` va `ALLOWED_HOSTS=["admin.example.uz"]` bo‘lishi kerak. PostgreSQL, Redis va `telegram-bot-api:8081` internetga ochilmasligi kerak. `.env` fayli Git repositoryga qo‘shilmaydi va serverda `chmod 600 .env` bilan himoyalanadi.

`TELEGRAM_API_HASH` va `BOT_TOKEN` maxfiy qiymatlardir. Ularni log, issue yoki Git commit ichiga yozmang. `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` BotFather tokenidan alohida bo‘lib, [my.telegram.org/apps](https://my.telegram.org/apps) sahifasida bir marta olinadi.

Instagram yoki YouTube login talab qiladigan kontent uchun `YTDLP_COOKIES_FILE` ishlatilishi mumkin, ammo cookie faylini repository yoki Docker image ichiga joylamaslik kerak. Uni secret mount orqali faqat worker konteyneriga read-only ulang.
