# Ekspluatatsiya va masshtablash

## Health va loglar

```bash
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
docker compose ps
docker compose logs --since=15m telegram-bot-api admin bot worker scheduler
```

`live` web jarayon ishlayotganini, `ready` PostgreSQL va Redis ulanishlari tayyorligini bildiradi. Loglarda bot tokeni, telefon raqami yoki to‘liq manba URL yozilmaydi. Nginx access logi admin magic-link tokeni oshkor bo‘lmasligi uchun o‘chirilgan.

Media ishlash vaqtini ajratib ko‘rish uchun worker logidagi `stage`, `elapsed_seconds`, `size_bytes` va `cache_hit` maydonlaridan foydalaning. Asosiy bosqichlar `probe`, `analysis`, `download`, `upload`, `cache_send` va `total`. `cache_hit=true` bo‘lgan so‘rovda manbadan download va FFmpeg ishlamaydi.

## Capacity

Aniq bir vaqtdagi foydalanuvchi soni server CPU, RAM, tarmoq, video hajmi va manba tezligiga bog‘liq. `WORKER_CONCURRENCY=4` bir worker konteynerida to‘rtta media taskni parallel bajaradi. Navbatdagi foydalanuvchilar botni ishlatishda davom etadi va Celery navbatida kutadi.

Boshlang‘ich production tavsiyasi:

| Resurs | Tavsiya |
|---|---|
| CPU | 4 vCPU |
| RAM | 8 GB |
| Disk | Kamida 100 GB SSD |
| Worker concurrency | 4 |
| Telegram limit | 2000 MB |

CPU 70–80% dan yuqori, RAM bosimi yoki navbat kutish vaqti doimiy oshsa worker replikasini ko‘paytiring:

```bash
docker compose up -d --scale worker=2
```

Bir hostda barcha workerlar bir xil `videos` bind mountdan foydalanadi, lekin har bir task UUID katalogida izolyatsiyalangan. Bir nechta EC2 instance ishlatilsa har worker o‘z lokal vaqtinchalik diskidan foydalanishi mumkin.

Bir xil URL, format va sifat parallel so‘ralsa Redis lock faqat bitta workerga manbadan yuklashga ruxsat beradi. Qolgan vazifalar qisqa intervalda keshni qayta tekshiradi va tayyor bo‘lgach Telegram `file_id` bilan yuboradi. `file_id` Bot tokeniga bog‘liq; token almashtirilsa eski kesh birinchi xatoda avtomatik bekor qilinib media qayta yuklanadi.

2 GB fayllar uchun disk hajmini parallel tasklar soniga qarab hisoblang. Worker media oqimlari va lokal Bot API vaqtinchalik nusxasi bir paytda mavjud bo‘lishi mumkin; `WORKER_CONCURRENCY=4` uchun kamida 20 GB bo‘sh operatsion zaxira qoldiring. Disk 80% ga yetganda ogohlantirish qo‘ying.

## Lokal Bot API holati

```bash
docker compose ps telegram-bot-api
docker compose logs --tail=100 telegram-bot-api
```

`TELEGRAM_API_ID` va `TELEGRAM_API_HASH` to‘ldirilmagan bo‘lsa konteyner sog‘lom holatga o‘tmaydi. Birinchi o‘tishda, xizmatlarni ko‘tarishdan oldin `make local-api-init` bir marta bajariladi. Botni yana Telegram bulut API’ga ulash kerak bo‘lsa, avval lokal serverdagi bot sessiyasini `close` qilish talab etiladi; ikki serverni bir token bilan parallel polling qilmang.

## Yangilash

```bash
docker compose pull
docker compose run --rm migrate
docker compose up -d --remove-orphans
docker image prune -f
```

`yt-dlp` tez-tez o‘zgaradigan tashqi platformalarga bog‘liq. Dependabot pull requestlarini CI’dan o‘tkazib muntazam deploy qilish kerak.

## Instagram TLS muammosi

Instagram so‘rovida `CERTIFICATE_VERIFY_FAILED` chiqsa, sertifikat issuerini tekshiring. Cisco Umbrella yoki OpenDNS sertifikati ko‘rinsa, worker `WORKER_DNS_PRIMARY` va `WORKER_DNS_SECONDARY` orqali bevosita public DNS resolverlardan foydalanadi. Standart qiymatlar `1.1.1.1` va `8.8.8.8`; tarmoq siyosati tashqi DNS’ni taqiqlasa, bu qiymatlarni Instagram’ni to‘g‘ri resolve qiladigan ichki resolverlarga almashtiring. Korporativ TLS proxy majburiy bo‘lsa, tashkilotning ishonchli CA sertifikatini host va konteyner trust store’iga o‘rnating. Sertifikat tekshiruvini o‘chirmang va `no-check-certificate` ishlatmang.

## Backup

Media fayllari backup qilinmaydi, chunki ular vaqtinchalik. PostgreSQL’dagi Telegram `file_id` keshi backup tarkibiga kiradi, ammo original media unda mavjud emas. PostgreSQL bazasi muntazam snapshot va point-in-time recovery bilan himoyalanishi kerak. Redis navbat va qisqa holatlar uchun ishlatiladi; AOF yoqilgan bo‘lsa-da, asosiy biznes ma’lumoti PostgreSQL’da saqlanadi.
