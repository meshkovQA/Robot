#!/bin/bash
echo "📄 Логи Robot Web Interface (Ctrl+C для выхода):"
echo "================================================"
sudo journalctl -u robot-web.service -f --no-pager