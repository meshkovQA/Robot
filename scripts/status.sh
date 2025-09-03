#!/bin/bash
SERVICE=robot-web.service
echo "🔍 Диагностика Robot Web Interface v2.1"
sudo systemctl status "$SERVICE" --no-pager -l
echo -e "\n📄 Последние логи:"
sudo journalctl -u "$SERVICE" --no-pager -n 20
IP=$(hostname -I | awk '{print $1}')
echo -e "\n🔗 Адреса:"
echo "Веб-интерфейс: http://$IP:5000"
echo "Видеопоток:   http://$IP:5000/camera/stream"
echo "API статус:   http://$IP:5000/api/status"