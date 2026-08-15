# MediaDownUzBot

YouTube va Instagram mediasini Telegram orqali yetkazib beruvchi, navbat asosida ishlaydigan production-ready xizmat.

## Imkoniyatlar

- Telegram kontakt orqali xavfsiz ro‘yxatdan o‘tish
- YouTube video, Shorts va Instagram post, Reel, Story, Highlight hamda Share havolalarini tekshirish
- YouTube uchun video sifati hamda MP3/M4A formatini taxminiy hajmi bilan tanlash
- Instagram foto, video, GIF va aralash carousel tarkibini asl sifatda avtomatik yuklash
- Lokal Telegram Bot API orqali 2 GB gacha fayl yuborish
- Celery worker orqali parallel media yuklash
- Mos bitta video/audio uchun Telegram `file_id` keshi: keyingi so‘rov qayta yuklanmasdan yuboriladi
- Bir xil parallel so‘rovlarni birlashtirish va media tahlili natijasini keshlash
- Worker va lokal Bot API orasida katta faylni HTTP orqali qayta ko‘chirmaydigan umumiy volume
- Faylni Telegram’ga yuborgach avtomatik o‘chirish
- Bot ichida murojaat yaratish, tarixni ko‘rish va administrator javobiga davomli reply yozish
- Faol foydalanuvchilarga holati kuzatiladigan ommaviy xabar yuborish
- PostgreSQL’dagi barcha 10 modul, qidiruv, filtr va sahifalashga ega himoyalangan admin panel
- PostgreSQL, Redis, Nginx, Docker Compose va Alembic migratsiyalari
- GitHub Actions orqali lint, test, security audit, image build va AWS deploy

## Arxitektura

```text
Telegram -> Lokal Bot API -> Bot -> PostgreSQL
                           -> Redis -> Celery worker -> yt-dlp/gallery-dl/Deno/FFmpeg
                                      |        |   |
                                      |        |   +-> YouTube PO-token provider
                                      |        +-> videos (vaqtinchalik umumiy volume)
                                      +-> Telegram file_id keshi -> Telegram

Admin -> Nginx -> FastAPI -> PostgreSQL -> notifications navbati -> Telegram
```

Worker media fayllarini faqat `videos/<job-uuid>/` ichida vaqtincha saqlaydi. Lokal Bot API shu volume’dagi faylni bevosita o‘qiydi. Telegram yuborishi muvaffaqiyatli yoki xatolik bilan tugashi bilan katalog tozalanadi. Media faylining o‘zi bazada saqlanmaydi; faqat URL’ning SHA-256 identifikatori, metama’lumot va Telegram bergan `file_id` saqlanadi. PostgreSQL’da telefon raqami va hali tugamagan vazifaning manba havolasi Fernet bilan shifrlangan holda saqlanadi.

## Talablar

- Docker Engine 24+
- Docker Compose 2.20+
- Telegram BotFather orqali olingan bot token
- [my.telegram.org](https://my.telegram.org/apps) orqali olingan Telegram `api_id` va `api_hash`
- Admin bo‘ladigan Telegram foydalanuvchi ID raqami

Deno, FFmpeg va media extractor runtime’lari Docker image ichiga pinlangan; host tizimga alohida o‘rnatish talab qilinmaydi.

## Lokal ishga tushirish

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`.env` ichida kamida quyidagilarni almashtiring:

```dotenv
BOT_TOKEN=BotFather_tokeni
TELEGRAM_API_ID=my_telegram_org_api_id
TELEGRAM_API_HASH=my_telegram_org_api_hash
ADMIN_TELEGRAM_IDS=[123456789]
FIELD_ENCRYPTION_KEY=generatsiya_qilingan_fernet_kalit
POSTGRES_PASSWORD=uzun_va_tasodifiy_parol
DATABASE_URL=postgresql+asyncpg://mediadown:shu_parol@postgres:5432/mediadown
ALEMBIC_DATABASE_URL=postgresql+psycopg://mediadown:shu_parol@postgres:5432/mediadown
```

So‘ng:

```bash
docker compose build
make local-api-init
docker compose up -d
docker compose ps
curl http://localhost:8080/health/ready
```

`make local-api-init` faqat lokal Bot API’ga birinchi o‘tishda bir marta bajariladi. U botning Telegram bulut Bot API sessiyasini yopadi. Keyin bot faqat Docker ichidagi, internetga porti ochilmagan lokal Bot API orqali ishlaydi.

Admin panel havolasi faqat `ADMIN_TELEGRAM_IDS` ro‘yxatidagi foydalanuvchiga botning `📊 Admin panel` tugmasi orqali beriladi. `/admin` bot buyrug‘i ro‘yxatdan chiqarilgan. Lokal Nginx manzili: [http://localhost:8080](http://localhost:8080).

## Test va sifat nazorati

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest
.venv/bin/bandit -c pyproject.toml -r app
.venv/bin/pip-audit
docker compose config --quiet
docker build -t mediadownuzbot:test .
```

## Masshtablash

Bir worker konteynerining parallel ishlari `WORKER_CONCURRENCY` bilan belgilanadi. Boshlang‘ich qiymat `4`. CPU, RAM, tarmoq va media sifatiga qarab worker replikalarini ko‘paytirish mumkin. Har bir foydalanuvchi uchun bir vaqtda bitta faol vazifa qabul qilinadi; bu botning bitta foydalanuvchi tomonidan band qilinishini cheklaydi.

Birinchi so‘rovda manbadan yuklash, zarur bo‘lsa FFmpeg birlashtirish va Telegram’ga upload qilish vaqti baribir tarmoq tezligiga bog‘liq. Mos bitta video yoki audio xuddi shu URL, format va sifat bilan keyin so‘ralsa bot Telegram `file_id` orqali odatda soniyalar ichida yuboradi. Birinchi foydalanuvchi o‘z chatidagi xabarni o‘chirishi keshni bekor qilmaydi. Carousel va ko‘p faylli postlar Telegram’da bir nechta `file_id` talab qilgani uchun hozircha manbadan qayta olinadi. Bir xil media bir vaqtda bir nechta foydalanuvchi tomonidan so‘ralsa, faqat bittasi yuklaydi; qolganlari natijani kutadi.

## Hujjatlar

- [Arxitektura va oqimlar](docs/architecture.md)
- [Qo‘llab-quvvatlash va ommaviy xabarlar](docs/support-and-broadcasts.md)
- [Konfiguratsiya](docs/configuration.md)
- [AWS deployment](docs/deployment-aws.md)
- [Ekspluatatsiya va masshtablash](docs/operations.md)
- [Xavfsizlik modeli](docs/security.md)

## Muhim cheklovlar

YouTube va Instagram extractor qoidalarini vaqti-vaqti bilan o‘zgartiradi. `yt-dlp`, `gallery-dl` va PO-token provider yangilanishlarini Dependabot hamda CI orqali muntazam tekshirish kerak. Har ikki platformada public, cookie, proxy va cookie+proxy yo‘llari zaruratga qarab avtomatik sinab ko‘riladi; eskirgan cookie oddiy public mediani bloklamaydi. PO-token challenge’ni yechishga yordam beradi, ammo server IP manzilining o‘zi cheklansa ishonchli outbound proxy talab qilinadi. Cookie sessiyasini serverda login/parol bilan xavfsiz va kafolatli avtomatik yangilab bo‘lmaydi; 2FA yoki challenge chiqqanda administrator uni qayta eksport qiladi. YouTube sifati yonidagi hajm manba bergan oqim hajmi yoki bitrate’dan hisoblangan taxminiy qiymat; yakuniy FFmpeg fayli biroz farq qilishi mumkin. Instagram Story va Highlight faqat hali mavjud hamda bot ko‘ra oladigan holatda yuklanadi; yopiq profil yoki login talab qiladigan media uchun workerga secret mount orqali Instagram cookie sessiyasi berilishi kerak. Shaxsiy, muddati tugagan, geo-cheklangan yoki har bir fayli 2 GB dan katta media yuborilmasligi mumkin. Foydalanuvchi yuklayotgan kontentga nisbatan mualliflik huquqi va platforma shartlariga rioya qilishi shart.
