#!/bin/bash

# Скрипт для паузы воспроизведения в Spotify

echo "⏸️ Пауза воспроизведения Spotify..."

if command -v playerctl &> /dev/null; then
    playerctl --player=spotify pause 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Музыка поставлена на паузу"
        exit 0
    fi
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    osascript -e 'tell application "Spotify" to pause' 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Музыка поставлена на паузу"
        exit 0
    fi
fi

if command -v dbus-send &> /dev/null; then
    dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Pause 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Музыка поставлена на паузу"
        exit 0
    fi
fi

echo "❌ Не удалось поставить на паузу"
exit 1