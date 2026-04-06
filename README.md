# Savely Bot 🤖

بوت تيليجرام لتحميل الفيديوهات بدون علامة مائية.

## 🚀 الرفع على Railway

### الخطوة 1: إنشاء البوت
1. افتح تيليجرام وابحث عن **@BotFather**
2. أرسل `/newbot`
3. اختر اسماً للبوت (مثلاً: Savely Downloader)
4. اختر username ينتهي بـ `bot` (مثلاً: `savely_dl_bot`)
5. احفظ الـ **TOKEN** الذي يعطيك إياه

### الخطوة 2: رفع على GitHub
```bash
git init
git add .
git commit -m "Savely Bot"
git remote add origin https://github.com/USERNAME/savely-bot.git
git push -u origin main
```

### الخطوة 3: النشر على Railway
1. اذهب إلى [railway.app](https://railway.app)
2. New Project → Deploy from GitHub → اختر الـ repo
3. بعد البناء: اذهب إلى **Variables**
4. أضف متغير: `BOT_TOKEN` = (الـ token من BotFather)
5. Railway سيعيد التشغيل تلقائياً

### الخطوة 4: تجربة البوت
ابحث في تيليجرام عن username البوت وأرسل `/start`

## ✨ المميزات
- يوتيوب، تيك توك، إنستغرام، تويتر، فيسبوك، +1000 موقع
- جودة حتى 1080p
- تحميل MP3
- حذف تلقائي من السيرفر
- رسائل خطأ واضحة بالعربي
