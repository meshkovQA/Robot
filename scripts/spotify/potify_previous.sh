#!/bin/bash

# Скрипт для переключения на предыдущий трек

echo "⏮️ Предыдущий трек..."

if command -v playerctl &> /dev/null; then
    playerctl --player=spotify previous 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Переключено на предыдущий трек"
        exit 0
    fi
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e 'tell application "Spotify" to previous track' 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Переключено на предыдущий трек"
        exit 0
    fi
fi

if command -v dbus-send &> /dev/null; then
    dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Previous 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Переключено на предыдущий трек"
        exit 0
    fi
fi

echo "❌ Не удалось переключить на предыдущий трек"
exit 1
