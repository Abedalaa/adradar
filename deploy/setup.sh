#!/bin/bash
# Run this ON THE SERVER, from inside /opt/adradar, after copying the code there.
# Usage: sudo ./deploy/setup.sh
set -e

APP_DIR="/opt/adradar"
cd "$APP_DIR"

if ! id -u adradar >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin adradar
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Needed only if you'll add platform="meta_scrape" competitors.
.venv/bin/playwright install --with-deps chromium

if [ ! -f .env ]; then
  cp .env.example .env
  echo "لسه محتاج تعدّل .env بالتوكنات الحقيقية بتاعتك قبل التشغيل."
fi

mkdir -p swipe_file
chown -R adradar:adradar "$APP_DIR"

cp deploy/adradar-web.service /etc/systemd/system/
cp deploy/adradar-pipeline.service /etc/systemd/system/
cp deploy/adradar-pipeline.timer /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now adradar-web.service
systemctl enable --now adradar-pipeline.timer

echo "تم. الداشبورد شغّال على المنفذ 5050، وسحب البيانات هيتكرر كل 12 ساعة."
echo "تحقق بـ: systemctl status adradar-web adradar-pipeline.timer"
