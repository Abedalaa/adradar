#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate

echo "===================================="
echo "         AdRadar"
echo "===================================="
echo ""

python main.py ingest
echo ""
python main.py classify
echo ""
echo "------- الإعلانات الأطول عمراً -------"
python main.py report longevity
echo ""
echo "------- توزيع زوايا الإعلانات -------"
python main.py report angles
echo ""
echo "===================================="
echo "انتهى. اضغط Enter عشان تقفل النافذة."
read
