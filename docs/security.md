# Xavfsizlik modeli

## Ma’lumotlar himoyasi

- Telefon raqami Fernet bilan shifrlanadi, admin jadvalida faqat oxirgi to‘rtta raqam ko‘rsatiladi.
- Media manba URL’i faqat vazifa tugaguncha shifrlangan holda saqlanadi va terminal holatda o‘chiriladi.
- Bot tokeni, database paroli va shifrlash kaliti environment secret sifatida beriladi.
- Admin login tokeni va session tokenining faqat SHA-256 hashi bazada saqlanadi.

## URL va media himoyasi

Faqat `youtube.com`, `youtu.be`, `instagram.com` va `instagr.am` ning aniq hostlari qabul qilinadi. URL credential, noodatiy port, subdomain aldovi, boshqa protocol va noma’lum pathlar rad etiladi. Instagram post, Reel, TV, Story, Highlight va Share pathlari allowlist asosida tekshiriladi. Ulashish tokeni va `story_media_id` xavfsiz formatda normalizatsiya qilinadi; URL tashqi extractor’ga faqat shu tekshiruvdan keyin uzatiladi.

Har task UUID katalogida ishlaydi. Path resolve tekshiruvi katalogdan chiqishni bloklaydi. Symlink va qo‘llab-quvvatlanmaydigan fayl kengaytmalari yuborilmaydi. Har bir fayl hajmi, YouTube video balandligi va task vaqti cheklangan.

## Admin himoyasi

- Admin ID allowlist bilan belgilanadi.
- Bot besh daqiqalik, bir martalik magic-link yaratadi.
- Session cookie `HttpOnly`, `SameSite=Strict`, production’da `Secure`.
- Logout so‘rovi HMAC asosidagi CSRF token bilan himoyalangan.
- CSP scriptlarni to‘liq taqiqlaydi, sahifa iframe ichida ochilmaydi.
- Admin javoblari browser cache’ida saqlanmaydi.
- Nginx login endpointiga rate limit qo‘llaydi va access logni yozmaydi.

## Konteyner himoyasi

Ilova `app` nomli non-root user bilan ishlaydi. Ilova konteynerlari read-only filesystem, `no-new-privileges` va barcha Linux capability’lar o‘chirilgan holda ishga tushadi. Workerga faqat `videos` katalogi write huquqi beriladi. YouTube PO-token provider porti hostga publish qilinmaydi, read-only filesystem va capability’siz ishlaydi. Cookie hamda ixtiyoriy proxy credentiallari logga chiqarilmaydi va repositoryga kiritilmaydi.

## Production tekshiruv ro‘yxati

- `COOKIE_SECURE=true` va HTTPS yoqilgan.
- PostgreSQL va Redis public internetdan yopilgan.
- `.env`, cookie fayli va backup kalitlari repositoryga kiritilmagan.
- `youtube-pot-provider` faqat ichki Docker tarmog‘idan foydalanadi.
- Proxy ishlatilsa, u shaxsiy va ishonchli providerga tegishli hamda credentiali secret sifatida saqlangan.
- AWS IAM role minimal huquqlar bilan cheklangan.
- CI’da Ruff, Pytest, Bandit, pip-audit va Docker build muvaffaqiyatli.
- Database va EBS backup siyosati yoqilgan.
- Bot komandalarida admin panel faqat allowlist IDlarga berilgan.
