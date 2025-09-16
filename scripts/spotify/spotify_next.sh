#!/bin/bash

# Скрипт для переключения на следующий трек

echo "⏭️ Следующий трек..."

if command -v playerctl &> /dev/null; then
    playerctl --player=spotify next 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Переключено на следующий трек"
        exit 0
    fi
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e 'tell application "Spotify" to next track' 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Переключено на следующий трек"
        exit 0
    fi
fi

if command -v dbus-send &> /dev/null; then
    dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Next 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Переключено на следующий трек"
        exit 0
    fi
fi

echo "❌ Не удалось переключить трек"
exit 1