WELCOME = (
    "👋 <b>Xush kelibsiz!</b>\n\n"
    "YouTube havolasida format va sifatni tanlaysiz. Instagram post, Reel, Story va Highlight "
    "videosi esa avtomatik ravishda eng yuqori mavjud sifatda yuboriladi."
)

REGISTRATION_REQUIRED = (
    "🔐 <b>Ro‘yxatdan o‘tish</b>\n\n"
    "Botdan foydalanish uchun quyidagi tugma orqali telefon raqamingizni yuboring."
)

CONTACT_INVALID = (
    "⚠️ <b>Telefon raqam tasdiqlanmadi</b>\n\n"
    "Faqat o‘zingizga tegishli Telegram kontaktini pastdagi tugma orqali yuboring."
)

PHONE_INVALID = (
    "⚠️ <b>Telefon raqam noto‘g‘ri</b>\n\n"
    "Telegram hisobingizga biriktirilgan haqiqiy telefon raqamni yuboring."
)

REGISTRATION_CANCELLED = (
    "❎ <b>Ro‘yxatdan o‘tish bekor qilindi.</b>\n\nQayta boshlash uchun /start buyrug‘ini yuboring."
)

REGISTRATION_SUCCESS = (
    "✅ <b>Ro‘yxatdan muvaffaqiyatli o‘tdingiz!</b>\n\n"
    "Endi YouTube yoki Instagram media havolasini yuboring."
)

URL_INVALID = (
    "❌ <b>Havola qabul qilinmadi</b>\n\n"
    "Faqat YouTube video/Shorts yoki Instagram post, Reel, Story, "
    "Highlight havolasini yuboring.\n\n"
    "<b>Misollar:</b>\n"
    "• https://youtu.be/VIDEO_ID\n"
    "• https://www.instagram.com/reel/SHORTCODE/\n"
    "• https://www.instagram.com/stories/USERNAME/STORY_ID/"
)

JOB_BUSY = (
    "⏳ <b>Oldingi so‘rovingiz hali yakunlanmadi.</b>\n\n"
    "Jarayon tugashini kuting yoki joriy vazifani bekor qiling."
)

ANALYZING = (
    "🔎 <b>Havola tekshirilmoqda...</b>\n\nVideo ma’lumotlari va mavjud sifatlar aniqlanmoqda."
)

STALE_ACTION = (
    "⌛ <b>Bu tugmaning amal qilish muddati tugagan.</b>\n\n"
    "Yangi havola yuborib, qaytadan urinib ko‘ring."
)

QUEUED = (
    "🕐 <b>Vazifa navbatga qo‘shildi.</b>\n\n"
    "Yuklab olish boshlanishi bilan holat avtomatik yangilanadi."
)

DOWNLOADING = "⬇️ <b>Media yuklab olinmoqda...</b>\n\nBu biroz vaqt olishi mumkin."
UPLOADING = "⬆️ <b>Telegram’ga yuborilmoqda...</b>\n\nIltimos, jarayon tugashini kuting."
CACHE_WAITING = (
    "⚡ <b>Shu media hozir tayyorlanmoqda...</b>\n\n"
    "Boshqa foydalanuvchi uchun boshlangan jarayon tugashi bilan sizga darhol yuboriladi."
)
JOB_CANCELLED = "🛑 <b>Vazifa bekor qilindi.</b>\n\nYangi havola yuborishingiz mumkin."

ADMIN_DENIED = "⛔ <b>Sizda admin panelga kirish huquqi yo‘q.</b>"
ADMIN_LINK = (
    "🔐 <b>Admin panel uchun bir martalik havola</b>\n\n"
    "Havola 5 daqiqa amal qiladi va faqat bir marta ishlatiladi. Uni boshqa shaxsga yubormang."
)

UNKNOWN_INPUT = (
    "ℹ️ YouTube yoki Instagram media havolasini yuboring.\n\n"
    "Yordam uchun /help buyrug‘idan foydalaning."
)

HELP = (
    "📚 <b>Botdan foydalanish</b>\n\n"
    "1. YouTube yoki Instagram havolasini yuboring.\n"
    "2. YouTube uchun video/audio va sifatni tanlang.\n"
    "3. Instagram post, Reel, Story yoki Highlight videosi avtomatik yuklanadi.\n"
    "4. Tayyor faylni Telegram orqali qabul qiling.\n\n"
    "Bir vaqtda bitta faol vazifa qabul qilinadi."
)

ERROR_MESSAGES = {
    "unsupported": "Bu havoladagi media qo‘llab-quvvatlanmaydi.",
    "unavailable": "Media o‘chirilgan yoki hozirda mavjud emas.",
    "private": "Yopiq yoki shaxsiy media yuklab olinmaydi.",
    "login_required": "Bu media ko‘rish uchun tizimga kirishni talab qiladi.",
    "geo_restricted": "Media hududiy cheklov sababli yuklab olinmadi.",
    "rate_limited": "Manba vaqtincha juda ko‘p so‘rov qabul qildi. Keyinroq urinib ko‘ring.",
    "too_large": "Fayl hajmi Telegram orqali yuborish uchun ruxsat etilgan 2 GB limitdan katta.",
    "timeout": "Yuklab olish uchun ajratilgan vaqt tugadi. Qayta urinib ko‘ring.",
    "upload_failed": "Fayl yuklandi, ammo Telegram’ga yuborib bo‘lmadi.",
    "cookies_required": "Manba ushbu media uchun qo‘shimcha tasdiqlash talab qildi.",
    "network": "Tarmoq bilan vaqtinchalik muammo yuz berdi. Qayta urinib ko‘ring.",
    "invalid_media": "Havolada yuklab olinadigan video yoki audio topilmadi.",
    "internal": "Kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko‘ring.",
}

QUALITY_TOO_LARGE = (
    "⛔ Bu sifatdagi fayl 2 GB limitdan katta. Kichikroq sifat yoki audio formatni tanlang."
)


def job_error_message(code: str) -> str:
    detail = ERROR_MESSAGES.get(code, ERROR_MESSAGES["internal"])
    return f"❌ <b>Vazifa yakunlanmadi</b>\n\n{detail}\n\nYangi havola yuborishingiz mumkin."
