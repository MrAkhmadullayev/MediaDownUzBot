# Arxitektura va ishlash oqimi

## Komponentlar

| Komponent | Vazifa |
|---|---|
| `bot` | Telegram polling, ro‘yxatdan o‘tish, URL va YouTube format tanlovi |
| `worker` | yt-dlp, gallery-dl, Deno EJS va FFmpeg orqali media tahlili, yuklash, konvertatsiya va Telegram upload |
| `telegram-bot-api` | Telegram bilan lokal Bot API aloqa qatlami va 2 GB gacha upload |
| `scheduler` | Qolib ketgan vaqtinchalik media kataloglarini tozalash |
| `admin` | FastAPI asosidagi statistika paneli va health endpointlar |
| `postgres` | Foydalanuvchi, vazifa, admin token, media metama’lumoti va Telegram `file_id` keshi |
| `redis` | FSM holati, foydalanuvchi va bir xil media locklari, Celery broker |
| `nginx` | Admin panel reverse proxy va login rate limit |

## Foydalanuvchi oqimi

1. Foydalanuvchi `/start` yuboradi.
2. Oldin ro‘yxatdan o‘tmagan bo‘lsa, Telegram kontaktini yuboradi.
3. Bot Telegram ID, ism va normalizatsiya qilingan telefonni ko‘rsatadi.
4. Tasdiqlangach, telefon raqami shifrlanib saqlanadi.
5. Foydalanuvchi YouTube yoki Instagram post, Reel, Story, Highlight yoxud Share havolasini yuboradi.
6. Xabar ichidan URL ajratiladi va qat’iy host hamda path qoidalari bo‘yicha normalizatsiya qilinadi. Telegram qatorga bo‘lib ko‘rsatgan Instagram host/path chegarasi va ko‘rinmas Unicode format belgilari xavfsiz tiklanadi. Instagram `/s/...` ulashish havolasidagi `story_media_id` aynan kerakli elementni belgilaydi.
7. Redis foydalanuvchiga bitta faol vazifa lockini beradi.
8. YouTube uchun worker media metama’lumotlar keshini tekshiradi; kerak bo‘lsa mavjud sifatlar va taxminiy hajmlarni tahlil qiladi. Instagram asl tarkibni tanlovsiz yuklash navbatiga o‘tadi. Davomiylik bo‘yicha cheklov qo‘llanmaydi.
9. YouTube uchun foydalanuvchi video/audio sifatini tanlaydi va 2 GB’dan katta variantlar bloklanadi. Instagram post tarkibidagi foto, video, GIF yoki carousel tartibi saqlanadi; har bir fayl 2 GB limitdan tekshiriladi.
10. Mos bitta video yoki audio uchun Telegram `file_id` mavjud bo‘lsa, media qayta yuklanmasdan darhol yuboriladi. Ko‘p faylli Instagram carousel manbadan olinib, Telegram chekloviga muvofiq 10 tadan albomlarga bo‘linadi.
11. Kesh yo‘q bo‘lsa worker bir xil media lockini oladi, faylni `videos/<uuid>/` ichiga bir marta yuklaydi va qolgan bir xil so‘rovlar natijani kutadi.
12. Lokal Bot API faylni umumiy read-only volume’dan bevosita o‘qib Telegram’ga yuboradi; worker bilan lokal API orasida yana bitta katta HTTP nusxasi yaratilmaydi.
13. Mos bitta video yoki audio uchun Telegram qaytargan `file_id` bazada saqlanadi va job `success` holatiga o‘tadi.
14. Manba URL bazadan o‘chiriladi, Redis lock bo‘shatiladi va vaqtinchalik katalog tozalanadi.

## Vazifa holatlari

```text
pending_analysis -> analyzing -> waiting_selection -> queued
                          |                     -> cancelled
                          +-----------------------> queued (Instagram)
queued -> downloading -> uploading -> success
                         |             |
                         +---- error <-+
```

Status faqat tegishli foydalanuvchiga bog‘langan UUID orqali o‘zgartiriladi. Takroriy callback yoki eskirgan tugma amaldagi holatga mos kelmasa rad etiladi.

## Parallel ishlash

Botning event loopi og‘ir media ishlarini bajarmaydi. `yt-dlp`, `gallery-dl`, YouTube EJS challenge’lari uchun pinlangan Deno va FFmpeg Celery workerda ishlaydi. Har worker jarayonida bir vaqtda bitta task bajariladi, konteynerdagi jarayonlar soni `WORKER_CONCURRENCY` orqali boshqariladi. Celery `acks_late`, `task_reject_on_worker_lost` va `prefetch=1` bilan sozlangan.

Lokal Bot API konteynerining `8081` porti hostga publish qilinmaydi. Bot va worker unga faqat Compose ichki tarmog‘i orqali ulanadi. Worker `videos` volume’iga yozadi, lokal Bot API esa uni read-only rejimda ko‘radi va `file://` yo‘li orqali faylni bevosita o‘qiydi. Muvaffaqiyat yoki xatolikdan keyin worker katalogi avtomatik tozalanadi.

`media_source_cache` YouTube tahlil natijasini vaqtincha saqlaydi. `telegram_file_cache` media faylini emas, mos bitta video yoki audio uchun Telegram’ning qayta ishlatiladigan `file_id` qiymatini saqlaydi. Kesh kaliti normalizatsiya qilingan URL’ning SHA-256 hashi, media turi va sifatdan iborat; to‘liq URL kesh jadvallariga yozilmaydi.
