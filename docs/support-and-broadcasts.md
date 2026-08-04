# Qo‘llab-quvvatlash va ommaviy xabarlar

## Foydalanuvchi murojaati

Asosiy klaviaturada `ℹ️ Yordam` yonida `💬 Qo‘llab-quvvatlash` tugmasi turadi. Bo‘lim ikkita amal beradi:

- `✍️ Murojaat qilish` ochiq murojaat bo‘lsa suhbatni davom ettiradi, bo‘lmasa yangi murojaat yaratadi.
- `🕘 Murojaatlar tarixi` foydalanuvchining barcha murojaatlarini sahifalab, administrator javoblari bilan ko‘rsatadi.

Murojaat faqat ro‘yxatdan o‘tgan Telegram foydalanuvchisiga tegishli bo‘ladi. Ticket UUID qiymati callback ichida yuboriladi, ammo har bir ko‘rish va javob yozish so‘rovida ticket egasi Telegram ID bo‘yicha bazada qayta tekshiriladi. Boshqa foydalanuvchining murojaatini taxmin qilingan UUID bilan ochib bo‘lmaydi.

Yangi foydalanuvchi xabari transaction bilan PostgreSQL’ga yoziladi. Shundan keyin administratorlarga ticket raqami, foydalanuvchi va dashboard havolasi bilan bildirishnoma `notifications` navbatiga beriladi. Bildirishnoma navbati vaqtincha ishlamasa murojaat yo‘qolmaydi: u dashboardda bazadan ko‘rinadi.

Administrator javobi avval `pending` holatida bazaga yoziladi, so‘ng worker Telegram’ga yuboradi. Natija quyidagicha audit qilinadi:

```text
pending -> sending -> sent
                  -> failed -> pending (qo‘lda qayta urinish)
```

Telegram yuborgan support javobining `message_id` qiymati saqlanadi. Foydalanuvchi o‘sha xabarga Telegram `Reply` qilsa, bot uni aynan tegishli ticketga qo‘shadi. Alohida yangi murojaat ochilmaydi. Yopilgan ticketga yangi xabar kelishi uni avtomatik qayta ochadi.

## Administrator dashboardi

`Murojaatlar` qismi ochiq va yopilgan ticketlarni, foydalanuvchi ma’lumotini, to‘liq suhbatni hamda har bir admin javobining yetkazish holatini ko‘rsatadi. Administrator quyidagilarni bajaradi:

1. Murojaatni ro‘yxatdan tanlaydi.
2. Javob matnini yozib yuboradi.
3. `sent` holatini yoki xato tafsilotini dashboardda ko‘radi.
4. Xato javobni qayta navbatga qo‘yadi.
5. Masala tugaganda ticketni yopadi; zarur bo‘lsa qayta ochadi.

Admin panelga botdagi `📊 Admin panel` tugmasidan bir martalik magic-link beriladi. Tugma faqat `ADMIN_TELEGRAM_IDS` ro‘yxatidagi ID uchun ko‘rinadi. `/admin` Telegram buyrug‘i mavjud emas.

## Ommaviy xabar

Administrator `Ommaviy xabar` qismida 3 500 belgigacha matn yozadi va brauzer tasdiqlash oynasidan keyin yuboradi. Xabar yaratilgan paytdagi `is_registered=true` va `is_active=true` foydalanuvchilar alohida delivery yozuvlariga snapshot qilinadi. Shu sababli yuborish davomida yangi ro‘yxatdan o‘tgan foydalanuvchi joriy broadcastga tasodifan qo‘shilmaydi.

Worker har oluvchi uchun natijani alohida saqlaydi va Telegram flood limitida `RetryAfter` muddatini kutadi. Dashboard quyidagilarni real ma’lumot bilan ko‘rsatadi:

- jami oluvchilar;
- muvaffaqiyatli yetkazilganlar;
- xatolar;
- broadcast holati va vaqtlar;
- yetkazilmagan oluvchilar uchun qayta urinish.

Foydalanuvchi botni bloklagan bo‘lsa Telegram `Forbidden` javobi olinadi, delivery `failed` bo‘ladi va foydalanuvchi nofaol belgilanadi. Qayta urinish faqat `sent` bo‘lmagan delivery yozuvlarini qayta ishlaydi.

## Ishonchlilik chegarasi

Yuborish transactionlari amalda at-least-once semantikada ishlaydi. Telegram xabarni qabul qilganidan keyin worker bazaga `sent` holatini yozishdan oldin majburan to‘xtasa, qo‘lda qayta urinish bir xil xabarni takror yuborishi mumkin. Odatdagi xato va retry holatlari idempotent himoyalangan; Telegram Bot API tashqi tizim bo‘lgani uchun mutlaq exactly-once kafolati mavjud emas.

Support va broadcast matnlari HTML escape qilinadi, shuning uchun administrator yoki foydalanuvchi kiritgan teglar Telegram markup sifatida bajarilmaydi. Dashboarddagi barcha yozuvchi POST amallari admin sessiyasi va CSRF tokeni bilan himoyalangan.
