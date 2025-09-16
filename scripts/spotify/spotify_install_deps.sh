#!/bin/bash

# Скрипт для установки зависимостей Spotify на разных системах

echo "🔧 Установка зависимостей для управления Spotify..."

# Определяем систему
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Система: Linux"
    
    # Ubuntu/Debian
    if command -v apt &> /dev/null; then
        echo "Установка playerctl через apt..."
        sudo apt update
        sudo apt install -y playerctl bc
    
    # Arch Linux
    elif command -v pacman &> /dev/null; then
        echo "Установка playerctl через pacman..."
        sudo pacman -S --noconfirm playerctl bc
    
    # Fedora/CentOS
    elif command -v dnf &> /dev/null; then
        echo "Установка playerctl через dnf..."
        sudo dnf install -y playerctl bc
    
    else
        echo "⚠️ Неизвестный дистрибутив Linux. Установите playerctl вручную."
    fi

elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Система: macOS"
    
    if command -v brew &> /dev/null; then
        echo "Установка через Homebrew..."
        brew install playerctl
    else
        echo "⚠️ Homebrew не найден. На macOS Spotify управляется через AppleScript."
        echo "Дополнительные зависимости не требуются."
    fi

else
    echo "⚠️ Неподдерживаемая система: $OSTYPE"
fi

echo "✅ Установка завершена. Проверьте работу командой: playerctl --version"