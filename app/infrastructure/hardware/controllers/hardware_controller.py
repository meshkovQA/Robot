# app/infrastructure/hardware/controllers/hardware_controller.py
# =======================================================================================
import time
import threading
import logging
from typing import Optional
from app.core.entities.command import RobotCommand
from app.core.events.event_bus import EventBus
from robot.i2c_bus import I2CBus, open_bus, FastI2CController

logger = logging.getLogger(__name__)


class HardwareController:
    def __init__(self, events: EventBus, bus: Optional[I2CBus] = None):
        self.events = events
        self._last_command_time = 0.0
        self._lock = threading.RLock()

        try:
            self.bus = bus if bus is not None else open_bus()
            self.fast_i2c = FastI2CController(self.bus)
            self._connected = True
            logger.info("✅ Hardware controller initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize hardware: {e}")
            self.bus = None
            self.fast_i2c = None
            self._connected = False
            raise

    def send_command(self, cmd: RobotCommand) -> bool:
        if not self._connected:
            return False

        try:
            with self._lock:
                data = cmd.pack_to_bytes()
                success = self.fast_i2c.write_command_sync(data, timeout=0.3)
                if success:
                    self._last_command_time = time.time()
                return success
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected

    def reconnect(self) -> bool:
        try:
            with self._lock:
                if self.fast_i2c:
                    self.fast_i2c.stop()
                if self.bus:
                    try:
                        self.bus.close()
                    except:
                        pass

                self.bus = open_bus()
                self.fast_i2c = FastI2CController(self.bus)
                self._connected = True
                return True
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            self._connected = False
            return False

    @property
    def last_command_time(self) -> float:
        with self._lock:
            return self._last_command_time

    def shutdown(self):
        with self._lock:
            if self.fast_i2c:
                self.fast_i2c.stop()
            if self.bus:
                try:
                    self.bus.close()
                except:
                    pass
            self._connected = False
