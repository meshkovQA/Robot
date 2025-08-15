#!/usr/bin/env python3
"""
Robot Controller для Raspberry Pi
Управление Arduino через I2C с двумя датчиками и танковыми поворотами
"""

import time
import struct
import smbus2
from dataclasses import dataclass
from typing import Optional

# I2C настройки
I2C_BUS = 1  # Raspberry Pi 4 использует bus 1
ARDUINO_ADDRESS = 0x08  # Адрес Arduino (8 в hex)


@dataclass
class RobotCommand:
    """Структура команды для Arduino (соответствует C++ struct)"""
    speed: int = 0          # Скорость -255 до 255
    direction: int = 0      # 0=стоп, 1=вперед, 2=назад, 3=танк влево, 4=танк вправо
    steering: int = 90      # Угол поворота сервы 0-180
    front_wheels: bool = True   # Включить передние колеса
    rear_wheels: bool = True    # Включить задние колеса


class RobotController:
    def __init__(self):
        """Инициализация контроллера робота"""
        try:
            self.bus = smbus2.SMBus(I2C_BUS)
            print("✅ I2C подключение установлено")
            time.sleep(0.5)  # Дать время Arduino проснуться
            self.test_connection()
        except Exception as e:
            print(f"❌ Ошибка I2C подключения: {e}")
            raise

    def test_connection(self) -> bool:
        """Проверка связи с Arduino"""
        try:
            # Попытка чтения данных датчиков
            front_dist, rear_dist = self.read_sensors()
            if front_dist != 999 or rear_dist != 999:
                print(
                    f"✅ Arduino отвечает. Датчики: передний={front_dist}см, задний={rear_dist}см")
                return True
            else:
                print("⚠️ Arduino подключен, но датчики не читаются")
                return False
        except Exception as e:
            print(f"❌ Arduino не отвечает: {e}")
            return False

    def send_command(self, command: RobotCommand) -> bool:
        """Отправка команды на Arduino через I2C"""
        try:
            print(f"🔧 Попытка отправить команду: {command}")

            # Упаковка как отдельные байты
            data = []

            # speed (2 байта, little-endian)
            speed_value = command.speed
            data.append(speed_value & 0xFF)  # Младший байт
            data.append((speed_value >> 8) & 0xFF)  # Старший байт

            # direction (2 байта)
            data.append(command.direction & 0xFF)
            data.append((command.direction >> 8) & 0xFF)

            # steering (2 байта)
            data.append(command.steering & 0xFF)
            data.append((command.steering >> 8) & 0xFF)

            # front_wheels (1 байт)
            data.append(1 if command.front_wheels else 0)

            # rear_wheels (1 байт)
            data.append(1 if command.rear_wheels else 0)

            print(f"🔧 Упакованные данные: {data} ({len(data)} байт)")

            # Отправка I2C данных
            if len(data) > 1:
                self.bus.write_i2c_block_data(
                    ARDUINO_ADDRESS, data[0], data[1:])
            else:
                self.bus.write_byte(ARDUINO_ADDRESS, data[0])

            print(f"📤 Команда отправлена успешно")
            return True

        except Exception as e:
            print(f"❌ Ошибка отправки команды: {e}")
            return False

    def read_sensors(self) -> tuple:
        """Чтение данных обоих датчиков с Arduino"""
        try:
            # Небольшая задержка перед чтением
            time.sleep(0.05)

            # Запрос 4 байт данных (2 датчика по 2 байта каждый)
            data = self.bus.read_i2c_block_data(ARDUINO_ADDRESS, 0, 4)
            print(f"🔍 I2C raw data: {data}")  # Отладка

            # Проверка валидности данных
            if len(data) != 4:
                print(f"⚠️ Неверная длина данных: {len(data)}")
                return 999, 999

            # Распаковка данных (little-endian)
            front_distance = (data[1] << 8) | data[0]  # Передний датчик
            rear_distance = (data[3] << 8) | data[2]   # Задний датчик

            # Проверка разумности значений
            if front_distance > 500 or rear_distance > 500:
                print(
                    f"⚠️ Подозрительные значения: front={front_distance}, rear={rear_distance}")
                return 999, 999

            print(
                f"📊 Датчики: передний={front_distance}см, задний={rear_distance}см")
            return front_distance, rear_distance

        except Exception as e:
            print(f"❌ Ошибка чтения датчиков: {e}")
            return 999, 999

    def move_forward(self, speed: int = 200) -> bool:
        """Движение вперед"""
        command = RobotCommand(speed=speed, direction=1, steering=90)
        return self.send_command(command)

    def move_backward(self, speed: int = 150) -> bool:
        """Движение назад"""
        command = RobotCommand(speed=speed, direction=2, steering=90)
        return self.send_command(command)

    def tank_turn_left(self, speed: int = 150) -> bool:
        """Танковый поворот влево"""
        command = RobotCommand(speed=speed, direction=3, steering=90)
        return self.send_command(command)

    def tank_turn_right(self, speed: int = 150) -> bool:
        """Танковый поворот вправо"""
        command = RobotCommand(speed=speed, direction=4, steering=90)
        return self.send_command(command)

    def turn_left(self, speed: int = 120, steering_angle: int = 10) -> bool:
        """Обычный поворот влево (рулем)"""
        command = RobotCommand(speed=speed, direction=1,
                               steering=steering_angle)
        return self.send_command(command)

    def turn_right(self, speed: int = 120, steering_angle: int = 170) -> bool:
        """Обычный поворот вправо (рулем)"""
        command = RobotCommand(speed=speed, direction=1,
                               steering=steering_angle)
        return self.send_command(command)

    def stop(self) -> bool:
        """Остановка робота"""
        command = RobotCommand(speed=0, direction=0, steering=90)
        return self.send_command(command)

    def set_steering(self, angle: int) -> bool:
        """Установка угла поворота без движения"""
        command = RobotCommand(speed=0, direction=0, steering=angle)
        return self.send_command(command)

    def emergency_stop(self) -> bool:
        """Экстренная остановка"""
        print("🚨 ЭКСТРЕННАЯ ОСТАНОВКА!")
        return self.stop()

    def get_status(self) -> dict:
        """Получение статуса робота"""
        front_dist, rear_dist = self.read_sensors()

        return {
            "front_distance": front_dist,
            "rear_distance": rear_dist,
            "obstacles": {
                "front": front_dist < 20 and front_dist != 999,
                "rear": rear_dist < 20 and rear_dist != 999
            },
            "sensor_error": front_dist == 999 or rear_dist == 999,
            "timestamp": time.time()
        }


def main():
    """Демонстрация управления роботом"""
    print("🤖 Запуск Robot Controller...")

    try:
        # Создание контроллера
        robot = RobotController()

        print("\n🎮 Демо-программа управления:")
        print("Команды: w=вперед, s=назад, a=танк влево, d=танк вправо")
        print("         q=поворот влево, e=поворот вправо, x=стоп, z=выход")

        while True:
            # Чтение статуса
            status = robot.get_status()

            # Отображение статуса
            if status['sensor_error']:
                print("⚠️ ОШИБКА ДАТЧИКОВ!")
            else:
                print(
                    f"📊 Датчики OK: Передний={status['front_distance']}см, Задний={status['rear_distance']}см")

                # Проверка препятствий
                if status['obstacles']['front']:
                    print("⚠️  ПРЕПЯТСТВИЕ СПЕРЕДИ!")
                if status['obstacles']['rear']:
                    print("⚠️  ПРЕПЯТСТВИЕ СЗАДИ!")

            # Ввод команды
            command = input("\nКоманда (w/s/a/d/q/e/x/z): ").lower().strip()

            if command == 'w':
                print("⬆️  Движение вперед")
                if status['obstacles']['front'] and not status['sensor_error']:
                    print("🚫 Движение заблокировано - препятствие спереди!")
                else:
                    robot.move_forward(200)

            elif command == 's':
                print("⬇️  Движение назад")
                if status['obstacles']['rear'] and not status['sensor_error']:
                    print("🚫 Движение заблокировано - препятствие сзади!")
                else:
                    robot.move_backward(150)

            elif command == 'a':
                print("🔄 Танковый поворот влево")
                robot.tank_turn_left()

            elif command == 'd':
                print("🔄 Танковый поворот вправо")
                robot.tank_turn_right()

            elif command == 'q':
                print("⬅️  Поворот влево (рулем)")
                robot.turn_left()

            elif command == 'e':
                print("➡️  Поворот вправо (рулем)")
                robot.turn_right()

            elif command == 'x':
                print("⏹️  Остановка")
                robot.stop()

            elif command == 'z':
                print("👋 Выход...")
                robot.stop()
                break

            elif command == 'test':
                # Скрытая команда для тестирования
                print("🔧 Тест I2C связи...")
                robot.test_connection()

            else:
                print("❓ Неизвестная команда. Используй: w/s/a/d/q/e/x/z")

            time.sleep(0.2)  # Задержка между командами

    except KeyboardInterrupt:
        print("\n🛑 Прерывание программы")
        robot.emergency_stop()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        try:
            robot.emergency_stop()
        except:
            pass


if __name__ == "__main__":
    main()
