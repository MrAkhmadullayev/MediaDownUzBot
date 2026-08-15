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
| `YTDLP_POT_PROVIDER_URL` | `http://youtube-pot-provider:4416` | Compose ichidagi YouTube PO-token provider manzili |
| `YTDLP_PROXY_URL` | bo‘sh | YouTube uchun ixtiyoriy HTTP(S) yoki SOCKS outbound proxy |
| `INSTAGRAM_PROXY_URL` | bo‘sh | Instagram uchun ixtiyoriy HTTP(S) yoki SOCKS outbound proxy |
| `LOG_LEVEL` | `INFO` | Log darajasi |

## Production qiymatlari

Production’da `APP_ENV=production`, `COOKIE_SECURE=true`, `ADMIN_BASE_URL=https://admin.example.uz` va `ALLOWED_HOSTS=["admin.example.uz"]` bo‘lishi kerak. PostgreSQL, Redis va `telegram-bot-api:8081` internetga ochilmasligi kerak. `.env` fayli Git repositoryga qo‘shilmaydi va serverda `chmod 600 .env` bilan himoyalanadi.

`TELEGRAM_API_HASH` va `BOT_TOKEN` maxfiy qiymatlardir. Ularni log, issue yoki Git commit ichiga yozmang. `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` BotFather tokenidan alohida bo‘lib, [my.telegram.org/apps](https://my.telegram.org/apps) sahifasida bir marta olinadi.

YouTube va Instagram ochiq mediani avval cookiesiz hamda proxysiz tekshiradi. Bu eskirgan brauzer sessiyasi yoki nosoz proxy public mediani buzishiga yo‘l qo‘ymaydi. Birinchi urinish cheklansa xizmat avtomatik ravishda cookie, keyin sozlangan proxy, so‘ng cookie va proxy birgalikdagi urinishga o‘tadi. `YTDLP_COOKIES_FILE` YouTube, `INSTAGRAM_COOKIES_FILE` esa Instagram sessiyasi uchun ishlatiladi. Cookie fayllarini repository, Docker image, log yoki chatga joylamang. Compose `./secrets` katalogini faqat worker konteyneridagi `/run/secrets` manziliga read-only ulaydi. Worker har bir vazifa uchun kerakli cookie faylining `0600` huquqli vaqtinchalik nusxasini yaratadi va vazifa tugagach uni avtomatik o‘chiradi; asl secret o‘zgartirilmaydi.

Compose `youtube-pot-provider` xizmatini ichki tarmoqda avtomatik ishga tushiradi. Uning porti hostga yoki internetga publish qilinmaydi. Standart `YTDLP_POT_PROVIDER_URL` qiymatini Compose deploymentida o‘zgartirish shart emas. PO-token JavaScript challenge uchun ishlaydi, lekin AWS public IP manzili YouTube tomonidan to‘liq cheklansa uni aylanib o‘tishga kafolat bermaydi. Bunday holatda faqat ishonchli, shaxsiy outbound proxy manzilini `YTDLP_PROXY_URL` sifatida kiriting. Instagram EC2 IP manzilini rate-limit qilsa alohida `INSTAGRAM_PROXY_URL` kiriting. Bepul yoki umumiy proxylardan foydalanmang va proxy credentiallarini secret deb hisoblang.

Brauzerdan o‘zingizga tegishli YouTube sessiyasini Netscape formatida eksport qilib, serverda quyidagicha saqlang:

```bash
cd /opt/mediadownuzbot
sudo install -d -m 700 -o ubuntu -g ubuntu secrets
sudo install -m 600 -o ubuntu -g ubuntu /xavfsiz/manba/youtube-cookies.txt secrets/youtube-cookies.txt
sudo install -m 600 -o ubuntu -g ubuntu /xavfsiz/manba/instagram-cookies.txt secrets/instagram-cookies.txt
```

Serverdagi `.env` fayliga quyidagini kiriting:

```dotenv
YTDLP_COOKIES_FILE=/run/secrets/youtube-cookies.txt
YTDLP_POT_PROVIDER_URL=http://youtube-pot-provider:4416
YTDLP_PROXY_URL=
INSTAGRAM_COOKIES_FILE=/run/secrets/instagram-cookies.txt
INSTAGRAM_PROXY_URL=
```

YouTube provider va worker xizmatini qayta yarating hamda holatini tekshiring:

```bash
sudo docker compose up -d --force-recreate youtube-pot-provider worker
sudo docker compose ps youtube-pot-provider worker
sudo docker compose exec worker test -r /run/secrets/youtube-cookies.txt
sudo docker compose exec worker test -r /run/secrets/instagram-cookies.txt
sudo docker compose logs --tail=100 youtube-pot-provider worker
```

Cookie eskirsa yangisini ayni fayl ustiga xavfsiz nusxalab, worker’ni qayta yarating. YouTube yoki Instagram cookie sessiyasini serverda login/parol bilan avtomatik yangilash ishonchli emas: platforma 2FA, captcha yoki challenge so‘rashi, akkauntni bloklashi mumkin. Shu sababli avtomatik tiklanish public/cookie/proxy failover orqali bajariladi, sessiyaning o‘zini yangilash esa administrator nazoratida qoladi. Cookie fayli mavjud bo‘lmasa yoki sessiya eskirsa bot foydalanuvchiga platformaga mos aniq tasdiqlash xabarini qaytaradi; bunday holat oddiy tarmoq xatosi sifatida ko‘rsatilmaydi. Proxy yoqilganda cookie aynan shu chiqish IP manzilida ishlatilishi tavsiya qilinadi, aks holda platforma sessiyani shubhali deb topishi mumkin.
