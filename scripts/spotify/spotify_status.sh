#!/bin/bash

# Скрипт для получения информации о текущем треке

echo "📊 Получение информации о треке..."

if command -v playerctl &> /dev/null; then
    # Получаем информацию о треке
    TITLE=$(playerctl --player=spotify metadata title 2>/dev/null)
    ARTIST=$(playerctl --player=spotify metadata artist 2>/dev/null)
    ALBUM=$(playerctl --player=spotify metadata album 2>/dev/null)
    STATUS=$(playerctl --player=spotify status 2>/dev/null)
    
    if [ $? -eq 0 ] && [ -n "$TITLE" ]; then
        echo "🎵 Трек: $TITLE"
        echo "👤 Исполнитель: $ARTIST"
        echo "💿 Альбом: $ALBUM"
        echo "▶️ Статус: $STATUS"
        exit 0
    fi
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    TRACK_INFO=$(osascript -e '
        tell application "Spotify"
            if it is running then
                set trackName to name of current track
                set artistName to artist of current track
                set albumName to album of current track
                set playerState to player state as string
                return trackName & " - " & artistName & " (" & albumName & ") [" & playerState & "]"
            else
                return "Spotify не запущен"
            end if
        end tell
    ' 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo "🎵 $TRACK_INFO"
        exit 0
    fi
fi

echo "❌ Не удалось получить информацию о треке"
exit 1
