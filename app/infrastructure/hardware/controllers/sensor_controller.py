# app/infrastructure/hardware/controllers/sensor_controller.py
# =======================================================================================
import time
import threading
import logging
from typing import Dict, Optional
from app.core.entities.sensor_data import SensorData
from app.core.events.event_bus import EventBus
from robot.config import SENSOR_ERR

logger = logging.getLogger(__name__)


class SensorManager:
    def __init__(self, hardware, events: EventBus, update_interval: float = 0.05):
        self.hardware = hardware
        self.events = events
        self.update_interval = update_interval
        self._sensor_cache = SensorData()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitoring = False

    def get_distance_sensors(self) -> Dict[str, int]:
        with self._lock:
            return {
                'center_front': self._sensor_cache.center_front,
                'left_front': self._sensor_cache.left_front,
                'right_front': self._sensor_cache.right_front,
                'left_rear': self._sensor_cache.left_rear,
                'right_rear': self._sensor_cache.right_rear,
            }

    def get_environmental_sensors(self) -> Dict[str, Optional[float]]:
        with self._lock:
            return {
                'temperature': self._sensor_cache.temperature,
                'humidity': self._sensor_cache.humidity,
            }

    def get_all_sensors(self) -> SensorData:
        with self._lock:
            return SensorData(
                center_front=self._sensor_cache.center_front,
                left_front=self._sensor_cache.left_front,
                right_front=self._sensor_cache.right_front,
                left_rear=self._sensor_cache.left_rear,
                right_rear=self._sensor_cache.right_rear,
                temperature=self._sensor_cache.temperature,
                humidity=self._sensor_cache.humidity,
                timestamp=self._sensor_cache.timestamp,
                valid=self._sensor_cache.valid
            )

    def start_monitoring(self):
        if self._monitoring:
            return
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self._monitoring = True

    def stop_monitoring(self):
        if not self._monitoring:
            return
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        self._monitoring = False

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            try:
                self._update_sensor_cache()
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in sensor monitoring: {e}")
                time.sleep(0.1)

    def _update_sensor_cache(self):
        try:
            if not self.hardware.is_connected():
                return

            fast_i2c = self.hardware.fast_i2c
            if hasattr(fast_i2c, 'cached_data'):
                cached_data = fast_i2c.cached_data
                with self._lock:
                    self._sensor_cache.center_front = cached_data.get(
                        'sensor_center_front', SENSOR_ERR)
                    self._sensor_cache.left_front = cached_data.get(
                        'sensor_left_front', SENSOR_ERR)
                    self._sensor_cache.right_front = cached_data.get(
                        'sensor_right_front', SENSOR_ERR)
                    self._sensor_cache.left_rear = cached_data.get(
                        'sensor_left_rear', SENSOR_ERR)
                    self._sensor_cache.right_rear = cached_data.get(
                        'sensor_right_rear', SENSOR_ERR)
                    self._sensor_cache.temperature = cached_data.get(
                        'env_temp')
                    self._sensor_cache.humidity = cached_data.get('env_hum')
                    self._sensor_cache.timestamp = time.time()
                    self._sensor_cache.valid = True
        except Exception as e:
            logger.error(f"Error updating sensor cache: {e}")
            with self._lock:
                self._sensor_cache.valid = False

    def shutdown(self):
        self.stop_monitoring()
