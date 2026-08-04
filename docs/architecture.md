# Arxitektura va ishlash oqimi

## Komponentlar

| Komponent | Vazifa |
|---|---|
| `bot` | Telegram polling, ro‘yxatdan o‘tish, URL va YouTube format tanlovi, foydalanuvchi murojaatlari |
| `worker` | `media` navbatida media ishlari, `notifications` navbatida support javoblari va ommaviy xabarlarni yetkazish |
| `youtube-pot-provider` | YouTube JavaScript challenge’lari uchun ichki PO-token xizmati |
| `telegram-bot-api` | Telegram bilan lokal Bot API aloqa qatlami va 2 GB gacha upload |
| `scheduler` | Qolib ketgan vaqtinchalik media kataloglarini tozalash |
| `admin` | FastAPI asosidagi statistika, murojaatlar va ommaviy xabarlar paneli hamda health endpointlar |
| `postgres` | Foydalanuvchi, vazifa, admin token, media keshi, murojaat, support xabari va broadcast audit ma’lumotlari |
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
8. YouTube uchun worker media metama’lumotlar keshini tekshiradi; kerak bo‘lsa mavjud sifatlar va taxminiy hajmlarni avval cookiesiz tahlil qiladi. Login talab qilinsa cookie bilan xavfsiz qayta urinadi, JavaScript challenge uchun ichki PO-token provider’dan foydalanadi. Instagram asl tarkibni tanlovsiz yuklash navbatiga o‘tadi. Davomiylik bo‘yicha cheklov qo‘llanmaydi.
9. YouTube uchun foydalanuvchi video/audio sifatini tanlaydi va 2 GB’dan katta variantlar bloklanadi. Instagram post tarkibidagi foto, video, GIF yoki carousel tartibi saqlanadi; har bir fayl 2 GB limitdan tekshiriladi.
10. Mos bitta video yoki audio uchun Telegram `file_id` mavjud bo‘lsa, media qayta yuklanmasdan darhol yuboriladi. Ko‘p faylli Instagram carousel manbadan olinib, Telegram chekloviga muvofiq 10 tadan albomlarga bo‘linadi.
11. Kesh yo‘q bo‘lsa worker bir xil media lockini oladi, faylni `videos/<uuid>/` ichiga bir marta yuklaydi va qolgan bir xil so‘rovlar natijani kutadi.
12. Lokal Bot API faylni umumiy read-only volume’dan bevosita o‘qib Telegram’ga yuboradi; worker bilan lokal API orasida yana bitta katta HTTP nusxasi yaratilmaydi.
13. Mos bitta video yoki audio uchun Telegram qaytargan `file_id` bazada saqlanadi va job `success` holatiga o‘tadi.
14. Manba URL bazadan o‘chiriladi, Redis lock bo‘shatiladi va vaqtinchalik katalog tozalanadi.

## Qo‘llab-quvvatlash oqimi

1. Foydalanuvchi `💬 Qo‘llab-quvvatlash` tugmasidan yangi murojaat yozadi yoki tarixdan avvalgi murojaatni ochadi.
2. Xabar `support_tickets` va `support_messages` jadvallariga yozilgach, administratorlarga `notifications` navbati orqali bildirishnoma keladi.
3. Administrator dashboarddagi suhbat oynasidan javob beradi. Javob bazaga avval `pending` holatida yoziladi, keyin worker Telegram’ga yuboradi va `sent` yoki `failed` holatini saqlaydi.
4. Foydalanuvchi botdagi javob xabariga Telegram `Reply` orqali javob bersa, `telegram_message_id` bo‘yicha aynan o‘sha murojaat topiladi. Yangi ticket ochilmaydi.
5. Yopilgan murojaatga foydalanuvchi yana yozsa, u qayta ochiladi va suhbat tarixi saqlanib qoladi.

## Ommaviy xabar oqimi

1. Administrator dashboardda matnni tasdiqlaydi.
2. Shu vaqtdagi barcha ro‘yxatdan o‘tgan va faol foydalanuvchilar `broadcast_deliveries` jadvaliga snapshot qilinadi.
3. `notifications` navbatidagi worker Telegram limitlarini hisobga olib foydalanuvchilarga ketma-ket yuboradi.
4. Har bir oluvchi uchun `pending`, `sending`, `sent` yoki `failed` natijasi saqlanadi; dashboard jami, yetkazilgan va xato sonini ko‘rsatadi.
5. Qisman yoki to‘liq xato bo‘lsa administrator faqat yetkazilmagan oluvchilar uchun qayta urinishni ishga tushiradi.

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

Botning event loopi og‘ir media yoki ommaviy yetkazish ishlarini bajarmaydi. `yt-dlp`, `gallery-dl`, pinlangan Deno, PO-token client va FFmpeg Celery workerda ishlaydi. Support va broadcast vazifalari `notifications`, media vazifalari `media` navbatiga yuboriladi. Alohida pinlangan `youtube-pot-provider` konteyneri faqat Compose ichki tarmog‘ida xizmat qiladi. Har worker jarayonida bir vaqtda bitta task bajariladi, konteynerdagi jarayonlar soni `WORKER_CONCURRENCY` orqali boshqariladi. Celery `acks_late`, `task_reject_on_worker_lost` va `prefetch=1` bilan sozlangan.

Lokal Bot API konteynerining `8081` porti hostga publish qilinmaydi. Bot va worker unga faqat Compose ichki tarmog‘i orqali ulanadi. Worker `videos` volume’iga yozadi, lokal Bot API esa uni read-only rejimda ko‘radi va `file://` yo‘li orqali faylni bevosita o‘qiydi. Muvaffaqiyat yoki xatolikdan keyin worker katalogi avtomatik tozalanadi.

`media_source_cache` YouTube tahlil natijasini vaqtincha saqlaydi. `telegram_file_cache` media faylini emas, mos bitta video yoki audio uchun Telegram’ning qayta ishlatiladigan `file_id` qiymatini saqlaydi. Kesh kaliti normalizatsiya qilingan URL’ning SHA-256 hashi, media turi va sifatdan iborat; to‘liq URL kesh jadvallariga yozilmaydi.
