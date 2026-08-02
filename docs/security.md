# Xavfsizlik modeli

## Ma’lumotlar himoyasi

- Telefon raqami Fernet bilan shifrlanadi, admin jadvalida faqat oxirgi to‘rtta raqam ko‘rsatiladi.
- Media manba URL’i faqat vazifa tugaguncha shifrlangan holda saqlanadi va terminal holatda o‘chiriladi.
- Bot tokeni, database paroli va shifrlash kaliti environment secret sifatida beriladi.
- Admin login tokeni va session tokenining faqat SHA-256 hashi bazada saqlanadi.

## URL va media himoyasi

Faqat `youtube.com`, `youtu.be` va `instagram.com` ning aniq hostlari qabul qilinadi. URL credential, noodatiy port, subdomain aldovi, boshqa protocol va noma’lum pathlar rad etiladi. Instagram ulashish tokeni faqat `highlight:<raqam>` formatida Base64URL orqali dekodlanadi. Highlight tarkibidan URL’dagi `story_media_id`ga mos aynan bitta media yozuvi qayta ishlanadi; qolgan playlist elementlari yuklanmaydi.

Har task UUID katalogida ishlaydi. Path resolve tekshiruvi katalogdan chiqishni bloklaydi. Symlink fayllar yuborilmaydi. Fayl hajmi, video balandligi va task vaqti cheklangan.

## Admin himoyasi

- Admin ID allowlist bilan belgilanadi.
- Bot besh daqiqalik, bir martalik magic-link yaratadi.
- Session cookie `HttpOnly`, `SameSite=Strict`, production’da `Secure`.
- Logout so‘rovi HMAC asosidagi CSRF token bilan himoyalangan.
- CSP scriptlarni to‘liq taqiqlaydi, sahifa iframe ichida ochilmaydi.
- Admin javoblari browser cache’ida saqlanmaydi.
- Nginx login endpointiga rate limit qo‘llaydi va access logni yozmaydi.

## Konteyner himoyasi

Ilova `app` nomli non-root user bilan ishlaydi. Ilova konteynerlari read-only filesystem, `no-new-privileges` va barcha Linux capability’lar o‘chirilgan holda ishga tushadi. Workerga faqat `videos` katalogi write huquqi beriladi.

## Production tekshiruv ro‘yxati

- `COOKIE_SECURE=true` va HTTPS yoqilgan.
- PostgreSQL va Redis public internetdan yopilgan.
- `.env`, cookie fayli va backup kalitlari repositoryga kiritilmagan.
- AWS IAM role minimal huquqlar bilan cheklangan.
- CI’da Ruff, Pytest, Bandit, pip-audit va Docker build muvaffaqiyatli.
- Database va EBS backup siyosati yoqilgan.
- Bot komandalarida admin panel faqat allowlist IDlarga berilgan.
