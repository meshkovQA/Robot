# app/services/robot/robot_orchestrator.py
# =======================================================================================
import time
import logging
from typing import Dict, Any, Optional
from app.core.events.event_bus import EventBus
from robot.config import IMU_ENABLED, LCD_ENABLED

logger = logging.getLogger(__name__)


class RobotOrchestrator:
    def __init__(self, hardware, sensors, navigation, camera, safety, events: EventBus, config: Dict[str, Any] = None):
        self.hardware = hardware
        self.sensors = sensors
        self.navigation = navigation
        self.camera = camera
        self.safety = safety
        self.events = events
        self.config = config or {}

        # Дополнительные компоненты
        self.imu = None
        self.lcd = None
        self._initialized = False

    def initialize(self) -> bool:
        if self._initialized:
            return True

        try:
            # IMU если включен
            if IMU_ENABLED:
                try:
                    from robot.devices.imu import MPU6500
                    self.imu = MPU6500()
                    if self.imu.start():
                        logger.info("✅ IMU initialized")
                    else:
                        self.imu = None
                except Exception as e:
                    logger.warning(f"IMU not available: {e}")

            # LCD если включен
            if LCD_ENABLED:
                try:
                    from robot.devices.lcd_display import RobotLCDDisplay
                    from robot.config import LCD_I2C_ADDRESS, LCD_UPDATE_INTERVAL
                    self.lcd = RobotLCDDisplay(
                        bus=None,
                        address=LCD_I2C_ADDRESS,
                        update_interval=LCD_UPDATE_INTERVAL,
                        robot_controller=self
                    )
                    logger.info("✅ LCD initialized")
                except Exception as e:
                    logger.warning(f"LCD not available: {e}")

            # Запускаем мониторинг датчиков
            self.sensors.start_monitoring()

            # Центрируем камеру
            self.camera.center()

            self._initialized = True
            logger.info("✅ Robot systems initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize robot: {e}")
            return False

    def get_full_status(self) -> Dict[str, Any]:
        try:
            movement = self.navigation.get_movement_status()
            camera_angles = self.camera.get_angles()
            sensor_data = self.sensors.get_all_sensors()

            return {
                'system': {
                    'initialized': self._initialized,
                    'timestamp': time.time()
                },
                'hardware': {
                    'connected': self.hardware.is_connected(),
                    'last_command_time': self.hardware.last_command_time
                },
                'movement': movement,
                'camera': {
                    'pan_angle': camera_angles[0],
                    'tilt_angle': camera_angles[1]
                },
                'sensors': {
                    'distances': self.sensors.get_distance_sensors(),
                    'environment': self.sensors.get_environmental_sensors(),
                    'valid': sensor_data.valid
                }
            }
        except Exception as e:
            return {'error': str(e), 'timestamp': time.time()}

    def emergency_stop(self) -> bool:
        logger.critical("🚨 EMERGENCY STOP!")
        try:
            return self.navigation.stop()
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
            return False

    def health_check(self) -> Dict[str, bool]:
        try:
            return {
                'hardware': self.hardware.is_connected(),
                'sensors': self.sensors.get_all_sensors().valid,
                'navigation': True,
                'camera': True,
                'safety': True,
                'imu': self.imu is not None,
                'lcd': self.lcd is not None
            }
        except Exception as e:
            return {'error': str(e)}

    def shutdown(self):
        logger.info("Shutting down robot...")
        try:
            self.navigation.shutdown()
            self.camera.shutdown()
            self.sensors.stop_monitoring()

            if self.imu:
                try:
                    self.imu.stop()
                except:
                    pass

            if self.lcd:
                try:
                    self.lcd.stop()
                except:
                    pass

            self.hardware.shutdown()
            self._initialized = False

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
