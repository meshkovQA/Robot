#!/bin/bash

# Скрипт для управления громкостью Spotify
# Принимает аргумент: up, down, или число от 0 до 100

COMMAND=$1
VOLUME=$2

echo "🔊 Управление громкостью: $COMMAND"

case $COMMAND in
    "up")
        if command -v playerctl &> /dev/null; then
            # Увеличиваем на 10%
            CURRENT=$(playerctl --player=spotify volume 2>/dev/null)
            if [ $? -eq 0 ]; then
                NEW=$(echo "$CURRENT + 0.1" | bc -l 2>/dev/null)
                if [ $(echo "$NEW > 1.0" | bc -l) -eq 1 ]; then
                    NEW="1.0"
                fi
                playerctl --player=spotify volume "$NEW" 2>/dev/null
                echo "✅ Громкость увеличена"
                exit 0
            fi
        fi
        ;;
    "down")
        if command -v playerctl &> /dev/null; then
            # Уменьшаем на 10%
            CURRENT=$(playerctl --player=spotify volume 2>/dev/null)
            if [ $? -eq 0 ]; then
                NEW=$(echo "$CURRENT - 0.1" | bc -l 2>/dev/null)
                if [ $(echo "$NEW < 0.0" | bc -l) -eq 1 ]; then
                    NEW="0.0"
                fi
                playerctl --player=spotify volume "$NEW" 2>/dev/null
                echo "✅ Громкость уменьшена"
                exit 0
            fi
        fi
        ;;
    [0-9]*)
        # Устанавливаем конкретное значение
        if [ "$COMMAND" -ge 0 ] && [ "$COMMAND" -le 100 ]; then
            VOLUME_DECIMAL=$(echo "scale=2; $COMMAND / 100" | bc -l)
            if command -v playerctl &> /dev/null; then
                playerctl --player=spotify volume "$VOLUME_DECIMAL" 2>/dev/null
                if [ $? -eq 0 ]; then
                    echo "✅ Громкость установлена на $COMMAND%"
                    exit 0
                fi
            fi
        fi
        ;;
esac

# Для macOS (osascript не поддерживает прямое управление громкостью Spotify)
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "⚠️ Управление громкостью на macOS ограничено"
fi

echo "❌ Не удалось изменить громкость"
exit 1