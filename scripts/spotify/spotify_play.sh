# Скрипт для воспроизведения музыки в Spotify

echo "🎵 Включение воспроизведения Spotify..."

# Проверяем систему и используем соответствующую команду
if command -v playerctl &> /dev/null; then
    # Linux с playerctl
    echo "Используем playerctl..."
    playerctl --player=spotify play 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Музыка включена через playerctl"
        exit 0
    fi
fi

# macOS с osascript
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Используем AppleScript для macOS..."
    osascript -e 'tell application "Spotify" to play' 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Музыка включена через AppleScript"
        exit 0
    fi
fi

# Попытка через D-Bus (Linux альтернатива)
if command -v dbus-send &> /dev/null; then
    echo "Используем D-Bus..."
    dbus-send --print-reply --dest=org.mpris.MediaPlayer2.spotify /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Play 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✅ Музыка включена через D-Bus"
        exit 0
    fi
fi

# Если ничего не сработало
echo "❌ Не удалось включить музыку. Убедитесь, что Spotify запущен."
exit 1