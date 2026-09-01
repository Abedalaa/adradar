#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

( sleep 1.5 && open "http://127.0.0.1:5050" ) &

echo "===================================="
echo "   AdRadar — لوحة التحكم"
echo "===================================="
echo "هتفتح تلقائياً في المتصفح خلال ثانية..."
echo "لو حبيت توقفها، ارجع هنا واضغط Control+C."
echo ""

python serve.py
