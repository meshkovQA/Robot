#!/usr/bin/env python3
"""
Веб-сервер для управления роботом
Танковое управление без рулевого сервомотора
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

# I2C настройки
I2C_BUS = 1
ARDUINO_ADDRESS = 0x08


@dataclass
class RobotCommand:
    """Структура команды для Arduino (упрощенная без рулевого управления)"""
    speed: int = 0
    direction: int = 0  # 0=стоп, 1=вперед, 2=назад, 3=поворот_влево, 4=поворот_вправо
    front_wheels: bool = True
    rear_wheels: bool = True


class RobotController:
    """Контроллер робота с танковым управлением"""

    def __init__(self):
        self.bus = None
        self.current_speed = 0
        self.is_moving = False  # Флаг движения
        self.movement_direction = 0  # Текущее направление движения
        self.last_command_time = time.time()
        self.monitoring_active = False  # Флаг мониторинга препятствий
        self.monitor_thread = None

        if I2C_AVAILABLE:
            try:
                self.bus = smbus2.SMBus(I2C_BUS)
                logger.info("I2C подключение установлено")
                time.sleep(0.5)
                self.start_obstacle_monitoring()
            except Exception as e:
                logger.error(f"Ошибка I2C подключения: {e}")
                self.bus = None

    def start_obstacle_monitoring(self):
        """Запуск потока мониторинга препятствий"""
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(
            target=self._obstacle_monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Запущен мониторинг препятствий")

    def _obstacle_monitor_loop(self):
        """Основной цикл мониторинга препятствий"""
        while self.monitoring_active:
            try:
                # Только для прямого движения
                if self.is_moving and self.movement_direction in [1, 2]:
                    front_dist, rear_dist = self.read_sensors()

                    # Проверка препятствий во время движения
                    should_stop = False
                    stop_reason = ""

                    if self.movement_direction == 1 and front_dist < 15 and front_dist != 999:
                        should_stop = True
                        stop_reason = f"Препятствие спереди: {front_dist}см"
                    elif self.movement_direction == 2 and rear_dist < 10 and rear_dist != 999:
                        should_stop = True
                        stop_reason = f"Препятствие сзади: {rear_dist}см"

                    if should_stop:
                        logger.warning(
                            f"Автоматическая остановка: {stop_reason}")
                        self._emergency_stop_internal()

                time.sleep(0.1)  # Проверка каждые 100мс
            except Exception as e:
                logger.error(f"Ошибка в мониторе препятствий: {e}")
                time.sleep(0.5)

    def _emergency_stop_internal(self):
        """Внутренняя экстренная остановка без изменения флага мониторинга"""
        self.current_speed = 0
        self.is_moving = False
        self.movement_direction = 0
        command = RobotCommand(speed=0, direction=0)
        self.send_command(command)

    def send_command(self, command: RobotCommand) -> bool:
        """Отправка команды на Arduino через I2C"""
        if not self.bus:
            logger.warning(f"I2C недоступен. Эмуляция команды: {command}")
            return True

        try:
            # Упаковка команды в байты (без рулевого управления)
            data = []
            speed_value = command.speed
            data.append(speed_value & 0xFF)
            data.append((speed_value >> 8) & 0xFF)
            data.append(command.direction & 0xFF)
            data.append((command.direction >> 8) & 0xFF)
            # Убираем steering - больше не используется
            data.append(90)  # Фиксированное значение для совместимости
            data.append(0)   # Фиксированное значение для совместимости
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
        """Чтение данных датчиков с Arduino"""
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

    def move_forward(self, speed) -> bool:
        """Движение вперед с заданной скоростью"""
        self.current_speed = speed
        self.is_moving = True
        self.movement_direction = 1
        command = RobotCommand(speed=speed, direction=1)
        return self.send_command(command)

    def move_backward(self, speed) -> bool:
        """Движение назад с заданной скоростью"""
        self.current_speed = speed
        self.is_moving = True
        self.movement_direction = 2
        command = RobotCommand(speed=speed, direction=2)
        return self.send_command(command)

    def tank_turn_left(self, speed) -> bool:
        """Танковый поворот влево"""
        command = RobotCommand(speed=speed, direction=3)
        return self.send_command(command)

    def tank_turn_right(self, speed) -> bool:
        """Танковый поворот вправо"""
        command = RobotCommand(speed=speed, direction=4)
        return self.send_command(command)

    def stop(self) -> bool:
        """Полная остановка"""
        self.current_speed = 0
        self.is_moving = False
        self.movement_direction = 0
        command = RobotCommand(speed=0, direction=0)
        return self.send_command(command)

    def shutdown(self):
        """Корректное завершение работы контроллера"""
        self.monitoring_active = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
        logger.info("Контроллер робота завершил работу")

    def update_speed(self, new_speed: int) -> bool:
        """
        Обновление скорости для движущегося робота
        Работает только если робот уже в движении
        """
        if not self.is_moving or self.movement_direction == 0:
            # Робот не движется - только обновляем переменную
            self.current_speed = new_speed
            logger.info(
                f"Скорость установлена на {new_speed}, но робот не движется")
            return True

        # Робот движется - обновляем скорость с сохранением направления
        self.current_speed = new_speed
        command = RobotCommand(
            speed=new_speed, direction=self.movement_direction)
        logger.info(
            f"Обновлена скорость до {new_speed} при движении в направлении {self.movement_direction}")
        return self.send_command(command)

    def start_movement_forward(self) -> bool:
        """Начать движение вперед с текущей скоростью"""
        if self.current_speed == 0:
            self.current_speed = 50  # Минимальная скорость по умолчанию
        return self.move_forward(self.current_speed)

    def start_movement_backward(self) -> bool:
        """Начать движение назад с текущей скоростью"""
        if self.current_speed == 0:
            self.current_speed = 50  # Минимальная скорость по умолчанию
        return self.move_backward(self.current_speed)

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
            "is_moving": self.is_moving,
            "movement_direction": self.movement_direction,
            "timestamp": time.time()
        }


# Глобальный экземпляр контроллера
robot = RobotController()

# Маршруты Flask


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/move/forward', methods=['POST'])
def api_move_forward():
    """API для движения вперед"""
    try:
        data = request.get_json() or {}
        speed = int(
            data.get('speed', robot.current_speed if robot.current_speed > 0 else 100))
        success = robot.move_forward(speed)
        return jsonify({
            'success': success,
            'direction': 'forward',
            'speed': speed,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_move_forward: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/move/backward', methods=['POST'])
def api_move_backward():
    """API для движения назад"""
    try:
        data = request.get_json() or {}
        speed = int(
            data.get('speed', robot.current_speed if robot.current_speed > 0 else 100))
        success = robot.move_backward(speed)
        return jsonify({
            'success': success,
            'direction': 'backward',
            'speed': speed,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_move_backward: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/turn/left', methods=['POST'])
def api_turn_left():
    """API для танкового поворота влево"""
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', 150))
        success = robot.tank_turn_left(speed)
        return jsonify({
            'success': success,
            'turn': 'left',
            'speed': speed,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_turn_left: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/turn/right', methods=['POST'])
def api_turn_right():
    """API для танкового поворота вправо"""
    try:
        data = request.get_json() or {}
        speed = int(data.get('speed', 150))
        success = robot.tank_turn_right(speed)
        return jsonify({
            'success': success,
            'turn': 'right',
            'speed': speed,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_turn_right: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/speed', methods=['POST'])
def api_update_speed():
    """API для обновления скорости"""
    try:
        data = request.get_json()
        new_speed = int(data.get('speed', 0))

        # Ограничение скорости
        new_speed = max(0, min(255, new_speed))

        success = robot.update_speed(new_speed)

        return jsonify({
            'success': success,
            'speed': robot.current_speed,
            'is_moving': robot.is_moving,
            'movement_direction': robot.movement_direction,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_update_speed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """API для остановки"""
    try:
        success = robot.stop()
        return jsonify({
            'success': success,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Ошибка в api_stop: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/emergency_stop', methods=['POST'])
def api_emergency_stop():
    """API для экстренной остановки"""
    try:
        success = robot.stop()
        logger.warning("Выполнена экстренная остановка!")
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
    logger.info("Запуск веб-сервера управления роботом (танковое управление)...")
    logger.info(f"I2C доступен: {I2C_AVAILABLE}")
    logger.info(f"I2C соединение: {'Активно' if robot.bus else 'Недоступно'}")

    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Ошибка запуска сервера: {e}")
    finally:
        # Корректное завершение работы
        robot.shutdown()
        logger.info("Сервер остановлен")


if __name__ == '__main__':
    main()
