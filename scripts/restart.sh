#!/bin/bash
echo "🔄 Перезапуск Robot Web Interface v2.1..."
sudo systemctl restart robot-web.service
sleep 3
sudo systemctl status robot-web.service --no-pager -l
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "🌐 Интерфейс доступен: http://$IP:5000"
echo "🎥 Видеопоток: http://$IP:5000/camera/stream"
echo "🧪 Тест камеры: python3 test_frame.py"