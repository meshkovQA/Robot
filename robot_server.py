#!/usr/bin/env python3
"""
Веб-сервер для управления роботом
Использует существующий RobotController
"""

from flask import Flask, render_template, request, jsonify
import time
import threading
import logging
from datetime import datetime

# Импорт существующего робота
try:
    import smbus2
    from dataclasses import dataclass
    I2C_AVAILABLE = True
except ImportError:
    print("Предупреждение: smbus2 недоступен. Работа в режиме эмуляции.")
    I2C_AVAILABLE = False

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# I2C настройки (из вашего кода)
I2C_BUS = 1
ARDUINO_ADDRESS = 0x08


@dataclass
class RobotCommand:
    """Структура команды для Arduino (из вашего кода)"""
    speed: int = 0
    direction: int = 0
    steering: int = 90
    front_wheels: bool = True
    rear_wheels: bool = True


class RobotController:
    """Контроллер робота на основе вашего кода"""

    def __init__(self):
        self.bus = None
        self.current_speed = 0
        self.current_steering = 90
        self.last_command_time = time.time()

        if I2C_AVAILABLE:
            try:
                self.bus = smbus2.SMBus(I2C_BUS)
                logger.info("I2C подключение установлено")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка I2C подключения: {e}")
                self.bus = None

    def send_command(self, command: RobotCommand) -> bool:
        """Отправка команды на Arduino через I2C (ваш метод)"""
        if not self.bus:
            logger.warning(f"I2C недоступен. Эмуляция команды: {command}")
            return True

        try:
            # Упаковка как отдельные байты (ваш алгоритм)
            data = []
            speed_value = command.speed
            data.append(speed_value & 0xFF)
            data.append((speed_value >> 8) & 0xFF)
            data.append(command.direction & 0xFF)
            data.append((command.direction >> 8) & 0xFF)
            data.append(command.steering & 0xFF)
            data.append((command.steering >> 8) & 0xFF)
            data.append(1 if command.front_wheels else 0)
            data.append(1 if command.rear_wheels else 0)

            if len(data) > 1:
                self.bus.write_i2c_block_data(
                    ARDUINO_ADDRESS, data[0], data[1:])
            else:
                self.bus.write_byte(ARDUINO_ADDRESS, data[0])

            self.last_command_time = time.time()
            return True

        except Exception as e:
            logger.error(f"Ошибка отправки команды: {e}")
            return False

    def read_sensors(self) -> tuple:
        """Чтение данных обоих датчиков с Arduino (ваш метод)"""
        if not self.bus:
            return 25, 30  # Эмуляция

        try:
            time.sleep(0.05)
            data = self.bus.read_i2c_block_data(ARDUINO_ADDRESS, 0, 4)

            if len(data) != 4:
                return 999, 999

            front_distance = (data[1] << 8) | data[0]
            rear_distance = (data[3] << 8) | data[2]

            if front_distance > 500 or rear_distance > 500:
                return 999, 999

            return front_distance, rear_distance

        except Exception as e:
            logger.error(f"Ошибка чтения датчиков: {e}")
            return 999, 999

    # Методы управления из вашего кода
    def move_forward(self, speed: int = 200) -> bool:
        self.current_speed = speed
        command = RobotCommand(speed=speed, direction=1,
                               steering=self.current_steering)
        return self.send_command(command)

    def move_backward(self, speed: int = 150) -> bool:
        self.current_speed = speed
        command = RobotCommand(speed=speed, direction=2,
                               steering=self.current_steering)
        return self.send_command(command)

    def tank_turn_left(self, speed: int = 150) -> bool:
        command = RobotCommand(speed=speed, direction=3, steering=90)
        return self.send_command(command)

    def tank_turn_right(self, speed: int = 150) -> bool:
        command = RobotCommand(speed=speed, direction=4, steering=90)
        return self.send_command(command)

    def turn_left(self, angle: int = 45) -> bool:
        self.current_steering = angle
        command = RobotCommand(speed=0, direction=5, steering=angle)
        return self.send_command(command)

    def turn_right(self, angle: int = 135) -> bool:
        self.current_steering = angle
        command = RobotCommand(speed=0, direction=6, steering=angle)
        return self.send_command(command)

    def stop(self) -> bool:
        self.current_speed = 0
        command = RobotCommand(speed=0, direction=0, steering=90)
        return self.send_command(command)

    def center_steering(self) -> bool:
        self.current_steering = 90
        command = RobotCommand(speed=0, direction=7, steering=90)
        return self.send_command(command)

    def set_movement(self, speed: int, steering: int) -> bool:
        """Универсальный метод установки движения"""
        self.current_speed = speed
        self.current_steering = steering

        if speed == 0:
            direction = 0  # Стоп
        elif speed > 0:
            direction = 1  # Вперед
        else:
            direction = 2  # Назад
            speed = abs(speed)

        command = RobotCommand(
            speed=speed, direction=direction, steering=steering)
        return self.send_command(command)

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
            "current_speed": self.current_speed,
            "current_steering": self.current_steering,
            "timestamp": time.time()
        }


# Глобальный экземпляр контроллера
robot = RobotController()

# Маршруты Flask


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/move', methods=['POST'])
def api_move():
    """API для универсального управления движением"""
    try:
        data = request.get_json()
        speed = int(data.get('speed', 0))
        steering = int(data.get('steering', 90))

        success = robot.set_movement(speed, steering)

        return jsonify({
            'success': success,
            'speed': speed,
            'steering': steering,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_move: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/command', methods=['POST'])
def api_command():
    """API для специфических команд"""
    try:
        data = request.get_json()
        command = data.get('command')
        value = data.get('value', None)

        success = False

        if command == 'move_forward':
            success = robot.move_forward(value or 50)
        elif command == 'move_backward':
            success = robot.move_backward(value or 50)
        elif command == 'tank_turn_left':
            success = robot.tank_turn_left(value or 50)
        elif command == 'tank_turn_right':
            success = robot.tank_turn_right(value or 50)
        elif command == 'turn_left':
            success = robot.turn_left(value or 10)
        elif command == 'turn_right':
            success = robot.turn_right(value or 140)
        elif command == 'stop':
            success = robot.stop()
        elif command == 'center_steering':
            success = robot.center_steering()
        else:
            return jsonify({'success': False, 'error': 'Unknown command'}), 400

        return jsonify({
            'success': success,
            'command': command,
            'value': value,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_command: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/emergency_stop', methods=['POST'])
def api_emergency_stop():
    """API для экстренной остановки"""
    try:
        success = robot.stop()
        return jsonify({
            'success': success,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_emergency_stop: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/status')
def api_status():
    """API для получения статуса системы"""
    try:
        status_data = robot.get_status()
        return jsonify({
            'success': True,
            'data': status_data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def main():
    """Основная функция запуска сервера"""
    logger.info("Запуск веб-сервера управления роботом...")
    logger.info(f"I2C доступен: {I2C_AVAILABLE}")
    logger.info(f"I2C соединение: {'Активно' if robot.bus else 'Недоступно'}")

    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False,
            threaded=True
        )
    except Exception as e:
        logger.error(f"Ошибка запуска сервера: {e}")


if __name__ == '__main__':
    main()
