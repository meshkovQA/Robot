#!/bin/bash
echo "🎥 Расширенное тестирование USB камеры..."
ls -la /dev/video* 2>/dev/null || echo "Видеоустройства не найдены"
for device in /dev/video*; do
  [[ -c "$device" ]] || continue
  echo "---- $device ----"
  v4l2-ctl --device="$device" --info 2>/dev/null | head -5 || true
  v4l2-ctl --device="$device" --list-formats-ext 2>/dev/null | head -10 || true
done