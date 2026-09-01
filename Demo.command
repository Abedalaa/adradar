#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

export ADRADAR_DEMO=1
export DATABASE_URL="sqlite:///adradar_demo.db"

rm -f adradar_demo.db

echo "===================================="
echo "   AdRadar — نسخة ديمو مضمونة"
echo "===================================="
echo "بتبني بيانات تجريبية واقعية من غير أي اتصال بـ Meta..."
echo ""

python main.py init-db
python main.py seed-demo

( sleep 1.5 && open "http://127.0.0.1:5050" ) &

echo ""
echo "الديمو هتفتح تلقائياً في المتصفح خلال ثانية..."
echo "لو حبيت توقفها، ارجع هنا واضغط Control+C."
echo ""

python serve.py
