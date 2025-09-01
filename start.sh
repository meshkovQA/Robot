#!/bin/bash
echo "🚀 Запуск Robot Web Interface v2.1..."
sudo systemctl start robot-web.service
sleep 2
sudo systemctl status robot-web.service --no-pager -l