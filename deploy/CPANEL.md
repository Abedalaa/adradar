# نشر AdRadar على cPanel (استضافة مشتركة)

هذا الدليل بديل عن `setup.sh` و ملفات `systemd`، اللي معمولة لسيرفر VPS
بصلاحيات root. على cPanel المشترك مفيش systemd ولا gunicorn — بيشتغل
عن طريق Passenger من خلال أداة **Setup Python App**.

## قبل ما تبدأ

- **الكود لازم يكون بره `public_html`**. لو حطيته جواه، الناس هتقدر
  تحمّل `.env` و `adradar.db` من المتصفح مباشرة.
- **الـ scraper (`platform="meta_scrape"`) مش هيشتغل هنا.** محتاج
  Playwright + متصفح Chromium، وده مش متاح على استضافة مشتركة.
  استخدم منصة `meta` (الـ API الرسمي) وسيب `playwright` مش متثبّت.

## الخطوات

### 1. ارفع الكود بره public_html

ارفع محتويات المشروع في `/home/USERNAME/adradar` (مش `public_html`).
احذف `__MACOSX` و `.DS_Store` و `.venv` — الأخير خاص بجهازك ومش
هينفع على السيرفر.

بنية المجلد المفروض تبقى كده:

    /home/USERNAME/adradar/
        passenger_wsgi.py     <-- نقطة دخول Passenger
        main.py               <-- الـ CLI (للـ cron)
        requirements-cpanel.txt   <-- ده اللي بيتثبّت هنا
        .env
        adradar/              <-- كود التطبيق
        swipe_file/

### 2. اعمل التطبيق من Setup Python App

cPanel > Software > **Setup Python App** > Create Application

| الحقل | القيمة |
|---|---|
| Python version | 3.11 (أو أحدث متاح) |
| Application root | `adradar` |
| Application URL | الدومين/الساب-دومين اللي عايزه |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

لو **Setup Python App مش موجودة** في لوحة cPanel، يبقى الاستضافة مش
بتدعم Python — راجع الفقرة الأخيرة.

### 3. ثبّت المكتبات

في حقل **Configuration files** اكتب `requirements-cpanel.txt` واضغط
Enter (الملف لازم يظهر في الليستة)، وبعدين دوس **Run Pip Install**.

استخدم `requirements-cpanel.txt` مش `requirements.txt` — الأولاني
مشيول منه `playwright` (محتاج Chromium ومكتبات نظام، مش متاحين على
استضافة مشتركة) و `gunicorn` (Passenger بياخد مكانه).

### 4. اضبط .env

عدّل `/home/USERNAME/adradar/.env`:

    DATABASE_URL=sqlite:////home/USERNAME/adradar/adradar.db
    META_ACCESS_TOKEN=<التوكن الجديد>
    ANTHROPIC_API_KEY=<المفتاح الجديد>
    FLASK_SECRET_KEY=<نص عشوائي طويل>
    SWIPE_FILE_DIR=/home/USERNAME/adradar/swipe_file

انتبه لأربع شرطات في `sqlite:////` — دي بتعني مسار مطلق.

### 5. شغّل واختبر

من صفحة التطبيق دوس **Restart**، وبعدين افتح الدومين. المفروض تشوف
شاشة "نظرة عامة" مش قائمة ملفات.

لو ظهر خطأ، الـ log بيبقى في `stderr.log` جوه مجلد التطبيق.

### 6. جدولة التحديث التلقائي

cPanel > Advanced > **Cron Jobs**. شوف `cpanel-cron.example` في نفس
المجلد ده للأمر بالظبط.

## لو Setup Python App مش موجودة

يبقى عندك اختيارين:

1. **اسأل الاستضافة** لو ممكن يفعّلوها (بعض الشركات بتفعّلها بالطلب).
2. **انقل لاستضافة تدعم Python** — أرخص حل هو VPS صغير، وساعتها
   `deploy/setup.sh` و ملفات systemd بتشتغل زي ما هي.

Flask **لا يشتغل** كملفات ثابتة أو عن طريق CGI بشكل عملي — لازم
Passenger أو WSGI server حقيقي.
